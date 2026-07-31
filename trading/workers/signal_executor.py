"""종가베팅 매수 집행 워커 (거래소별 2회, 종가 매수).

종목의 NXT 상장 여부(ka10100 nxtEnable)에 따라 각 거래소의 종가에 매수한다:
  --venue krx (15:00~15:20)  → NXT 불가 종목을 KRX 종가(15:20 동시호가)에 매수
  --venue nxt (19:30~19:50)  → NXT 가능 종목을 NXT 종가(19:50)에 매수

매수 타이밍(종가 단일 매수): 윈도우 시작에 시드를 한 번 배분해 종목별 매수 수량을 확정한 뒤,
데드라인(15:20/19:50)에 전 종목을 시장가/IOC 로 매수한다. 윈도우 동안은 하트비트만 남긴다
(대시보드 가동 표시). closing_bet 엣지가 종가→익일시가로 측정·검증되므로 진입가를 종가에 맞춘다.
  · 과거 '눌림 추종'(고점 대비 -BUY_PULLBACK_PCT% 조기 매수)을 썼으나, 2026-07-20 실거래
    표본 분석에서 데드라인 대비 평균 -0.27%(KRX -0.44%) 손해로 나와 종가 단일 매수로 회귀.
    빠지는 종목만 조기 확정하는 구조적 비대칭이 원인. 데드라인 폴백이 이미 추세 종목을 확보한다.

배분: 종가랩 시드배분기 로직(등가중 + 잔여 그리디 재투입)으로, 해당 거래소 대상 후보
전체에 가용현금(시드)을 윈도우 시작 시점에 한 번에 배분한다(수량은 이후 고정).
멱등성 키로 중복 방지(워커 재기동 안전), 윈도우 가드로 오실행 방지, blocklist 제외.
"""
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.seed_allocator import allocate
from core.regime_gate import seed_multiplier
from core.futures_gate import sector_keep_factors, effective_keep, gated_shares
from core.macro_gate import macro_keep
from core.config import SEED_COMBINED_MIN_MULT, REALTIME_FEED_ENABLED
from core.kiwoom_data_client import to_int
from core.repository import trade_signal as signal_repo
from core.repository import order as order_repo
from core.repository import blocklist as blocklist_repo
from core.repository import risk_config as risk_config_repo
from core.repository import leverage_map as leverage_map_repo
from core.repository import audit_log

setup_logging()
logger = logging.getLogger("SignalExecutor")

POLL_SEC = 15  # closing_bet 완료 대기 / 데드라인 대기 하트비트 공통 주기
NXT_PARTIAL_RETRY_MAX = 2
NXT_PARTIAL_RETRY_WAIT_SEC = 3
# 체결통보(WS 00)를 받았는데 ka10076 체결내역이 아직 안 보일 때 재조회 대기(초).
# 브로커 조회 반영이 통보보다 느린 구간을 넘기기 위한 짧은 유예다.
FILL_REQUERY_WAIT_SEC = 0.5

# 체결통보 구독(core.realtime_feed) — NXT 데드라인 집행 구간에만 살아 있다.
# 모듈 변수로 두는 이유: _retry_nxt_partial_fill 시그니처를 바꾸지 않아 기존 호출·테스트가
# 그대로 유효하고, 피드가 없으면(None) 종전 '3초 대기 후 조회' 동작과 완전히 동일하다.
_fill_feed = None


def resolve_leverage_target(sig: dict, lev_map: dict) -> tuple[dict, dict | None]:
    """레버리지 ETF 대체매수 치환.

    lev_map: {원종목코드: {"etf_cd", "etf_nm"}} (leverage_map.get_active_map()).
    신호 종목이 매핑에 있으면 종목코드/이름을 ETF 로 바꾼 새 sig 를 돌려준다. 신호 id 는 그대로라
    상태 갱신은 원신호 행에 남고(종가랩엔 원종목), 사이징·주문·포지션·청산은 ETF 로 흐른다.
    치환은 is_nxt_enabled 조회 '전'에 하므로 거래소 라우팅도 ETF 기준(원종목이 NXT 가능이어도
    ETF 가 NXT 불가면 KRX 종가로 매수). 반환: (sig_or_swapped, swap_info|None).
    """
    src = sig["stk_cd"]
    m = lev_map.get(src)
    if not m or not m.get("etf_cd"):
        return sig, None
    swapped = {**sig, "stk_cd": m["etf_cd"], "stk_nm": m.get("etf_nm") or m["etf_cd"]}
    return swapped, {"src_cd": src, "src_nm": sig.get("stk_nm"),
                     "etf_cd": m["etf_cd"], "etf_nm": m.get("etf_nm")}


def _beat(payload: dict) -> None:
    """매수 폴링 하트비트 — 대시보드 '모니터' 탭이 매수 워커 가동 여부를 판별하는 신호.
    기록 실패가 매수 루프를 막지 않도록 예외를 삼킨다(순수 로깅)."""
    try:
        audit_log.append("buy_poll", None, payload)
    except Exception as e:
        logger.warning("하트비트 기록 실패: %s", e)

# (venue → 윈도우 시작/데드라인/대기한도(시,분), 거래소). ecosystem.config.js 의 cron(=start) 과 일치시킬 것.
# wait_until: closing_bet(같은 분 동시 기동) 완료를 이 시각까지 기다린다. 미감지 시 기존 시그널로 진행
#   (윈도우 전체를 놓치지 않도록). closing_bet 소요시간(보통 수 분)을 고려해 데드라인 전 여유를 둔다.
VENUES = {
    "krx": {"exchange": "KRX", "start": (15, 0),  "wait_until": (15, 12), "deadline": (15, 20)},   # KRX 종가 직전 정규장, NXT 불가 종목
    "nxt": {"exchange": "NXT", "start": (19, 30), "wait_until": (19, 42), "deadline": (19, 50)},  # NXT 종가 직전, NXT 가능 종목
}


def _hm(now: datetime) -> tuple[int, int]:
    return (now.hour, now.minute)


def _deadline_dt(now: datetime, hm: tuple[int, int]) -> datetime:
    return now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)


def _start_fill_feed(venue: str):
    """NXT 데드라인 집행 직전에 체결통보(WS `00`) 구독을 시작한다. 실패 시 None.

    시세(0B)는 구독하지 않는다 — 여기서 필요한 건 '방금 낸 IOC 주문이 체결됐는가'뿐이고,
    가격은 데드라인에 한 번만 쓰므로 REST 로 충분하다. KRX(동시호가)는 부분체결 재시도가
    없어 대상이 아니다."""
    if venue != "nxt" or not REALTIME_FEED_ENABLED:
        return None
    try:
        from core.realtime_feed import KiwoomRealtimeFeed

        feed = KiwoomRealtimeFeed(symbols={}, subscribe_fills=True)
        feed.start()
        logger.info("체결통보 구독 시작 — NXT 부분체결 확인에 사용")
        return feed
    except Exception as e:
        logger.warning("체결통보 구독 실패 — 종전 %d초 대기 방식으로 계속: %s",
                       NXT_PARTIAL_RETRY_WAIT_SEC, e)
        return None


def _wait_for_fill_signal(seconds: float) -> bool:
    """체결통보를 최대 seconds 초 기다린다. 통보를 받으면 즉시 True.

    피드가 없으면 종전처럼 그냥 seconds 초 대기하고 False — 이 경로에서는 동작이
    이전과 완전히 같다(대기 후 ka10076 조회)."""
    if _fill_feed is None:
        time.sleep(seconds)
        return False
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _fill_feed.take_fill_signal():
            return True
        time.sleep(0.1)
    return False


def _execution_qty_by_order(client, stk_cd: str, ord_nos: list[str], exchange: str) -> tuple[dict[str, int], bool]:
    """키움 체결내역에서 주문번호별 누적 체결수량을 읽는다.

    조회 실패는 재시도를 막는 쪽으로 처리한다. 잔량 재주문은 실제 체결 수량을 알아야만 안전하다.
    """
    wanted = {str(o) for o in ord_nos if o}
    if not wanted:
        return {}, True
    stex_tp = "2" if exchange == "NXT" else "1"
    try:
        resp = client.get_executions(qry_tp="1", sell_tp="2", stk_cd=stk_cd, stex_tp=stex_tp)
    except Exception as e:
        logger.warning("부분체결 조회 실패 [%s]: %s", stk_cd, e)
        return {}, False

    qty_by_order: dict[str, int] = {o: 0 for o in wanted}
    for row in resp.get("cntr", []) or []:
        ono = str(row.get("ord_no") or "")
        if ono not in wanted:
            continue
        qty_by_order[ono] += to_int(row.get("cntr_qty"))
    return qty_by_order, True


def _retry_nxt_partial_fill(engine: ExecutionEngine, trade_date: str, sig: dict,
                            target_qty: int, price: int, initial_resp: dict,
                            deadline_hm: tuple[int, int]) -> dict:
    """NXT 최유리 IOC 부분체결 잔량을 마감 전 소량 재시도한다.

    execute_buy 의 기본 멱등키는 원주문 1회용이라, 잔량 재시도는 별도 멱등키
    (:partial:N)로 주문 행을 남긴다. 체결 반영은 기존 fills_sync 가 주문번호 기준으로 처리한다.
    """
    result = {"attempts": 0, "filled": None, "remaining": None, "order_nos": []}
    if getattr(engine.client, "paper", True):
        return result

    stk_cd = sig["stk_cd"]
    initial_ord_no = initial_resp.get("ord_no")
    if not initial_ord_no or target_qty < 1:
        return result

    deadline = _deadline_dt(datetime.now(), deadline_hm)
    order_nos = [str(initial_ord_no)]
    base_key = ExecutionEngine.idempotency_key(trade_date, sig["id"], "buy")

    for attempt in range(1, NXT_PARTIAL_RETRY_MAX + 1):
        now = datetime.now()
        if now + timedelta(seconds=NXT_PARTIAL_RETRY_WAIT_SEC + 1) >= deadline:
            break
        # 체결통보를 기다린다(오면 즉시). 피드가 없으면 종전과 같이 고정 대기.
        notified = _wait_for_fill_signal(NXT_PARTIAL_RETRY_WAIT_SEC)

        qty_by_order, ok = _execution_qty_by_order(engine.client, stk_cd, order_nos, "NXT")
        if ok and notified and not any(qty_by_order.values()):
            # 통보는 왔으니 체결은 분명히 있었는데 ka10076 이 아직 반영 전이다.
            # 종전엔 이걸 '체결내역 미확인'으로 보고 재시도를 포기해 잔량을 놓쳤다 → 짧게 재조회.
            time.sleep(FILL_REQUERY_WAIT_SEC)
            qty_by_order, ok = _execution_qty_by_order(engine.client, stk_cd, order_nos, "NXT")
        if not ok:
            audit_log.append("buy_partial_retry_skip", stk_cd, {
                "reason": "체결내역 조회 실패", "target_qty": target_qty, "order_nos": order_nos})
            break

        filled = sum(qty_by_order.values())
        remaining = max(0, target_qty - filled)
        result.update({"filled": filled, "remaining": remaining, "order_nos": list(order_nos)})
        if remaining < 1:
            break

        # 체결 row 가 하나도 안 보이면 API 지연 가능성이 있어 과매수를 피하려고 재주문하지 않는다.
        if filled == 0 and all(q == 0 for q in qty_by_order.values()):
            audit_log.append("buy_partial_retry_skip", stk_cd, {
                "reason": "체결내역 미확인", "target_qty": target_qty, "order_nos": order_nos})
            break
        if len(order_nos) > 1 and qty_by_order.get(order_nos[-1], 0) == 0:
            audit_log.append("buy_partial_retry_skip", stk_cd, {
                "reason": "최근 재시도 체결내역 미확인", "target_qty": target_qty,
                "filled": filled, "order_nos": order_nos})
            break

        retry_price = engine.data.get_market_price(stk_cd) or price
        key = f"{base_key}:partial:{attempt}"
        if order_repo.find_by_idempotency_key(key):
            logger.info("부분체결 재시도 중복 스킵 [%s] %s", stk_cd, key)
            continue

        decision = engine.risk.check(trade_date, stk_cd, remaining * retry_price)
        if not decision.allowed:
            audit_log.append("buy_partial_retry_blocked", stk_cd, {
                "key": key, "reason": decision.reason, "remaining": remaining})
            logger.warning("부분체결 잔량 재시도 차단 [%s]: %s", stk_cd, decision.reason)
            break

        order_id = order_repo.create_intended(
            key, sig["id"], stk_cd, "buy", remaining, retry_price, "market", "live"
        )
        audit_log.append("buy_partial_retry_intended", stk_cd, {
            "order_id": order_id, "remaining": remaining, "price": retry_price,
            "filled": filled, "target_qty": target_qty})
        resp = engine.client.buy(
            stk_cd, remaining, 0,
            trde_tp=ExecutionEngine._now_trde_tp("NXT"),
            dmst_stex_tp="NXT",
        )
        audit_log.append("buy_response", stk_cd, {"order_id": order_id, "resp": resp})
        if resp.get("return_code") != 0 or not resp.get("ord_no"):
            order_repo.mark_sent(order_id, None, "rejected")
            audit_log.append("buy_rejected", stk_cd, {"order_id": order_id, "resp": resp})
            logger.warning("부분체결 잔량 재시도 거부 [%s] %d주: %s",
                           stk_cd, remaining, resp.get("return_msg"))
            break

        order_repo.mark_sent(order_id, resp.get("ord_no"), "sent")
        engine.risk.record_order(trade_date)
        order_nos.append(str(resp["ord_no"]))
        result.update({"attempts": attempt, "order_nos": list(order_nos)})
        audit_log.append("buy_partial_retry_sent", stk_cd, {
            "order_id": order_id, "remaining": remaining, "ord_no": resp.get("ord_no"),
            "attempt": attempt})
        logger.info("NXT 부분체결 잔량 재시도 [%s] %d주 (시도 %d/%d)",
                    stk_cd, remaining, attempt, NXT_PARTIAL_RETRY_MAX)

    return result


def _buy_candidate(engine: ExecutionEngine, trade_date: str, c: dict,
                   exchange: str, reason: str, deadline_hm: tuple[int, int]) -> None:
    """배분 수량으로 1종목 매수 집행 + 시그널 상태 갱신. 한 종목당 1회만 호출한다."""
    sig, stk, price = c["sig"], c["stk_cd"], c["price"]
    sized = {**sig, "_qty": c["shares"], "_price": price}
    logger.info("매수 집행 [%s] %d주 @%d (%s)", stk, c["shares"], price, reason)
    try:
        signal_repo.update_status(sig["id"], "executing")
        resp = engine.execute_buy(trade_date, sized, dmst_stex_tp=exchange)
        partial = {}
        if resp and exchange == "NXT":
            partial = _retry_nxt_partial_fill(
                engine, trade_date, sig, c["shares"], price, resp, deadline_hm
            )
        note = None
        if partial.get("filled") is not None and partial.get("remaining"):
            note = f"NXT 부분체결 추정 {partial['filled']}/{c['shares']}주, 잔량 재시도 {partial.get('attempts', 0)}회"
        signal_repo.update_status(sig["id"], "done" if resp else "skipped", note=note)
        audit_log.append("buy_exec", stk, {
            "shares": c["shares"], "price": price, "reason": reason, "sent": bool(resp),
            "partial_retry": partial or None})
    except Exception as e:
        logger.error("시그널 %s 집행 실패: %s", sig["id"], e)
        signal_repo.update_status(sig["id"], "rejected", note=str(e))
        audit_log.append("buy_exec", stk, {
            "shares": c["shares"], "price": price, "reason": reason, "sent": False, "error": str(e)})
    finally:
        c["bought"] = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", choices=["krx", "nxt"], required=True)
    args = parser.parse_args()
    cfg = VENUES[args.venue]

    now = datetime.now()
    if now.weekday() >= 5 or not (cfg["start"] <= _hm(now) <= cfg["deadline"]):
        logger.info("[%s] 매수 윈도우(평일 %02d:%02d~%02d:%02d)가 아님 — 스킵 (현재 %s)",
                    args.venue.upper(), *cfg["start"], *cfg["deadline"], now.strftime("%a %H:%M"))
        return 0

    trade_date = now.strftime("%Y%m%d")
    logger.info("매수 집행 시작 [%s] 거래소=%s 윈도우 %02d:%02d~%02d:%02d 종가 매수 (거래일 %s)",
                args.venue.upper(), cfg["exchange"], *cfg["start"], *cfg["deadline"], trade_date)
    audit_log.append("buy_start", None, {
        "venue": args.venue, "exchange": cfg["exchange"],
        "window": f"{cfg['start'][0]:02d}:{cfg['start'][1]:02d}~{cfg['deadline'][0]:02d}:{cfg['deadline'][1]:02d}"})

    # 0) closing_bet(같은 분 동시 기동) 완료 대기 — 윈도우 시작 이후 갱신된 시그널이 보일 때까지.
    #    이 회차 closing_bet 가 종목 추천을 마친 뒤의 최신 시그널로 매수하기 위함.
    since = now.replace(hour=cfg["start"][0], minute=cfg["start"][1],
                        second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    while not signal_repo.has_fresh_signals(trade_date, since):
        if _hm(datetime.now()) >= cfg["wait_until"]:
            logger.warning("closing_bet 갱신 미감지 — 대기한도(%02d:%02d) 도달, 기존 시그널로 진행",
                           *cfg["wait_until"])
            break
        logger.info("closing_bet(%02d:%02d 회차) 완료 대기 중... (%s 이후 갱신 대기)",
                    *cfg["start"], since)
        _beat({"venue": args.venue, "phase": "wait"})
        time.sleep(POLL_SEC)
    else:
        logger.info("closing_bet 갱신 시그널 감지 — 매수 폴링 시작")

    signals = signal_repo.get_pending_signals(trade_date)
    if not signals:
        logger.info("집행 대기 시그널 없음 — 종료")
        _beat({"venue": args.venue, "phase": "done", "reason": "집행 대기 시그널 없음"})
        return 0

    block = blocklist_repo.get_codes()
    # 레버리지 ETF 대체매수 매핑 (토글 off 면 빈 dict → 현행 동작 그대로).
    lev_map = (leverage_map_repo.get_active_map()
               if risk_config_repo.get_risk_config().get("LEVERAGE_ENABLED", 0) else {})
    engine = ExecutionEngine()
    want_nxt = args.venue == "nxt"

    # 1) 전체 pending 후보의 거래소·점수 분류 (blocklist 제외, 레버리지 치환)
    #    다른 거래소 몫의 현금을 예약하려면 전체 점수합이 필요하다.
    classified = []  # (sig, stk, score, is_nxt)
    for sig in signals:
        stk = sig["stk_cd"]
        # blocklist 는 원종목 기준으로 검사(레버리지 치환 전) — 수동 보유분 자동매수 차단 의미.
        if stk in block:
            logger.info("blocklist 제외 — signal %s [%s]", sig["id"], stk)
            signal_repo.update_status(sig["id"], "skipped", note="blocklist")
            audit_log.append("buy_skip", stk, {"reason": "blocklist"})
            continue
        # 레버리지 치환: is_nxt_enabled 조회 전에 하므로 거래소 라우팅도 ETF 기준.
        if lev_map:
            sig, swap = resolve_leverage_target(sig, lev_map)
            if swap:
                logger.info("레버리지 치환 [%s→%s] signal %s", swap["src_cd"], swap["etf_cd"], sig["id"])
                audit_log.append("leverage_swap", swap["src_cd"], {"signal_id": sig["id"], **swap})
                stk = sig["stk_cd"]
        classified.append((sig, stk, max(float(sig.get("score") or 0), 0),
                           engine.data.is_nxt_enabled(stk)))
    if not classified:
        logger.info("대상 시그널 없음 — 종료")
        _beat({"venue": args.venue, "phase": "done", "reason": "대상 시그널 없음"})
        return 0

    total_score = sum(s for _, _, s, _ in classified)
    venue_items = [(sig, stk, score) for (sig, stk, score, isn) in classified if isn == want_nxt]
    if not venue_items:
        logger.info("이 거래소 대상 시그널 없음 — 종료")
        _beat({"venue": args.venue, "phase": "done", "reason": "이 거래소 대상 시그널 없음"})
        return 0
    venue_score = sum(s for _, _, s in venue_items)

    # 2) 시드 = 가용현금의 점수비례 몫 (다른 거래소 몫은 예약, 해당 시간대에 집행)
    #    현금주문가능금액(100stk_ord_alow_amt)을 쓴다 — 종가베팅은 당일 매도대금을
    #    종가에 재투입하므로 미정산 매도분을 제외하는 ord_alow_amt 는 시드를 과소산정한다.
    cash = to_int(engine.client.get_deposit().get("100stk_ord_alow_amt"))
    seed = int(cash * venue_score / total_score) if total_score > 0 else 0
    logger.info("가용현금 %d × (거래소점수 %.0f / 전체 %.0f) → 시드 %d원, 후보 %d종목",
                cash, venue_score, total_score, seed, len(venue_items))

    # 최초 시드 배율(대시보드 설정) — base 시드에 곱해 레짐/거시/선물 게이트 감액보다 먼저 적용.
    #   0.0~1.0 축소 전용. 기본 1.0 이면 현행 동작 그대로. 게이트와 독립(곱셈 순서만 앞).
    seed_init_mult = risk_config_repo.get_risk_config().get("SEED_INIT_MULT", 1.0)
    if seed_init_mult < 1.0:
        before_init = seed
        seed = int(seed * seed_init_mult)
        logger.info("최초 시드 배율 적용: 시드 %d → %d원 (배율 %.3f)", before_init, seed, seed_init_mult)

    # 롤링 엣지 게이트 — 최근 선정 종목의 점수 판별력이 역전된 레짐이면 총 시드를 축소.
    #   등가중 사이징이라 조절 대상은 개별 비중이 아니라 총 노출(seed). 배분 로직은 불변.
    mult, regime = seed_multiplier()
    before = seed
    if mult < 1.0:
        seed = int(seed * mult)
        logger.info("레짐 게이트 적용: 시드 %d → %d원 (배수 %.3f, 스프레드 %s)",
                    before, seed, mult, regime.get("split"))
    # 미개입(1.0)이어도 매 판단을 기록 — 게이트 성적을 사후 채점(백테스트)할 관찰 로그.
    audit_log.append("regime_gate", None,
                     {"venue": args.venue, "multiplier": mult, "seed_init_mult": seed_init_mult,
                      "seed_before": before, "seed_after": seed, **regime})

    # 3) 윈도우 시작 시점 현재가로 시드 배분 → 종목별 매수 수량 확정 (이후 수량 고정)
    cands: list[dict] = [
        {"sig": sig, "stk_cd": stk, "score": score,
         "price": engine.data.get_market_price(stk), "bought": False}
        for sig, stk, score in venue_items
    ]
    allocate(seed, cands)

    # 거시 이벤트 게이트 — 보유 창(매수→익일 시가)에 sev3 예정 이벤트(FOMC·CPI·고용)가 걸려 있으면
    #   총 노출 축소. 프록시(VIX·WTI·환율)는 관찰 전용으로 진단만 기록. 미개입 포함 매 판단을 audit.
    m_keep, macro = macro_keep(args.venue)
    audit_log.append("macro_gate", None,
                     {"seed": seed, "regime_mult": mult, **macro})

    # 선물 환경 게이트(섹터 차등, NXT 전용) — 배분 뒤 섹터별 keep-factor 로 수량 감액(reduce-only).
    #   NQ·야간선물 하락 시 고베타 섹터(반도체·IT)를 더, 방어주(통신·음식료)를 덜 깎는다.
    #   그 시점 선물값+섹터별 keep 은 audit 로 스냅샷(추후 섹터×선물 실측·재튜닝용).
    factors, futures = sector_keep_factors(args.venue, [c["stk_cd"] for c in cands])
    detail = futures.get("detail") or {}
    for c in cands:
        raw = factors.get(c["stk_cd"], 1.0)
        # 선물(섹터별) × 거시(공통) 곱에 레짐 결합 하한(SEED_COMBINED_MIN_MULT) 반영
        keep = effective_keep(raw * m_keep, mult)
        if keep < 1.0:
            before_sh = c["shares"]
            c["shares"] = gated_shares(c["shares"], keep)  # 반올림 감액(mild 컷이 1주를 0으로 안 만듦)
            c["cost"] = c["shares"] * c["price"]
            logger.info("게이트 감액 [%s] keep=%.3f(선물 %.3f × 거시 %.3f): %d → %d주",
                        c["stk_cd"], keep, raw, m_keep, before_sh, c["shares"])
        # 감사: 실제 적용 keep 과 원본 섹터 keep(연구용) 둘 다 기록
        if c["stk_cd"] in detail:
            detail[c["stk_cd"]]["keep_raw"] = raw
            detail[c["stk_cd"]]["keep"] = keep
    if futures.get("gated"):
        audit_log.append("futures_gate", None,
                         {"seed": seed, "regime_mult": mult,
                          "combined_min_mult": SEED_COMBINED_MIN_MULT, **futures})

    # 배분 0주는 즉시 스킵 처리
    for c in cands:
        if c["shares"] < 1:
            logger.info("배분 0주 스킵 [%s] (점수 %.1f, 현재가 %d)", c["stk_cd"], c["score"], c["price"])
            signal_repo.update_status(c["sig"]["id"], "skipped", note="배분 0주")
            audit_log.append("buy_skip", c["stk_cd"], {
                "reason": "배분 0주", "score": c["score"], "price": c["price"]})
            c["bought"] = True  # 루프 대상에서 제외

    # 4) 데드라인까지 대기 — 종가 매수라 트리거 없이 하트비트만 남긴다(대시보드 가동 표시).
    while _hm(datetime.now()) < cfg["deadline"]:
        _beat({"venue": args.venue, "phase": "poll",
               "pending": sum(1 for c in cands if not c["bought"])})
        time.sleep(POLL_SEC)

    # 5) 데드라인 — 잔여 후보 전량 종가(KRX 동시호가 / NXT IOC) 매수
    #    NXT 는 부분체결 확인에 체결통보를 쓰므로 집행 직전에 구독을 열고, 끝나면 반드시 닫는다.
    global _fill_feed
    _fill_feed = _start_fill_feed(args.venue)
    try:
        for c in cands:
            if c["bought"]:
                continue
            try:
                cur = engine.data.get_market_price(c["stk_cd"])
                if cur > 0:
                    c["price"] = cur  # 체결 기록용 참고가(실주문은 시장가/IOC)
            except Exception as e:
                logger.warning("데드라인 현재가 조회 실패 [%s]: %s", c["stk_cd"], e)
            _buy_candidate(engine, trade_date, c, cfg["exchange"], "종가 매수(마감 데드라인)",
                           cfg["deadline"])
    finally:
        if _fill_feed is not None:
            _fill_feed.stop()
            _fill_feed = None

    # 6) 관리자 알림은 체결 직후 fills_sync 워커가 실체결가로 전송한다
    #    (KRX 15:31 / NXT 19:55) — 종가 단일가/IOC 체결가는 이 시점엔 아직 미확정이라 여기서 보내지 않는다.
    logger.info("매수 집행 종료 [%s]", args.venue.upper())
    return 0


if __name__ == "__main__":
    from core.market_calendar import exit_if_not_trading_day
    # cron 은 평일만 돌지만 평일 공휴일(휴장)은 못 거른다 — 진입부에서 한 번 더 차단.
    exit_if_not_trading_day()
    sys.exit(main())
