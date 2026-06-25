"""종가베팅 매수 집행 워커 (거래소별 2회, 윈도우 눌림 매수).

종목의 NXT 상장 여부(ka10100 nxtEnable)에 따라 각 거래소의 종가 직전 윈도우에 매수한다:
  --venue krx (15:00~15:20)  → NXT 불가 종목을 KRX 종가 직전 정규장에 매수
  --venue nxt (19:30~19:50)  → NXT 가능 종목을 NXT 종가 직전에 매수

매수 타이밍(눌림 추종): 윈도우 시작에 시드를 한 번 배분해 종목별 매수 수량을 확정한 뒤,
15초마다 폴링하며 종목별 장중 고점(윈도우 시작 후 갱신)을 추종한다. 현재가가 고점 대비
BUY_PULLBACK_PCT% 만큼 눌리면 그 자리에서 즉시 시장가/IOC 로 매수한다(매도 트레일링 스탑의 매수 버전).
끝까지 안 눌린 종목은 데드라인(15:20/19:50)에 시장가로 매수해 추세 종목을 놓치지 않는다.

배분: 종가랩 시드배분기 로직(점수 가중 비례 + 잔여 그리디 재투입)으로, 해당 거래소 대상 후보
전체에 가용현금(시드)을 윈도우 시작 시점에 한 번에 배분한다(이후 가격이 눌려도 수량은 고정).
멱등성 키로 중복 방지(워커 재기동 안전), 윈도우 가드로 오실행 방지, blocklist 제외.
"""
import sys
import time
import argparse
import logging
from datetime import datetime

from core.config import BUY_PULLBACK_PCT
from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.seed_allocator import allocate
from core.kiwoom_data_client import to_int
from core.repository import trade_signal as signal_repo
from core.repository import blocklist as blocklist_repo

setup_logging()
logger = logging.getLogger("SignalExecutor")

POLL_SEC = 15  # closing_bet 완료 대기 / 눌림 매수 폴링 공통 주기

# (venue → 윈도우 시작/데드라인/대기한도(시,분), 거래소). ecosystem.config.js 의 cron(=start) 과 일치시킬 것.
# wait_until: closing_bet(같은 분 동시 기동) 완료를 이 시각까지 기다린다. 미감지 시 기존 시그널로 진행
#   (윈도우 전체를 놓치지 않도록). closing_bet 소요시간(보통 수 분)을 고려해 데드라인 전 여유를 둔다.
VENUES = {
    "krx": {"exchange": "KRX", "start": (15, 0),  "wait_until": (15, 12), "deadline": (15, 20)},   # KRX 종가 직전 정규장, NXT 불가 종목
    "nxt": {"exchange": "NXT", "start": (19, 30), "wait_until": (19, 42), "deadline": (19, 50)},  # NXT 종가 직전, NXT 가능 종목
}


def _hm(now: datetime) -> tuple[int, int]:
    return (now.hour, now.minute)


def _buy_candidate(engine: ExecutionEngine, trade_date: str, c: dict,
                   exchange: str, reason: str) -> None:
    """배분 수량으로 1종목 매수 집행 + 시그널 상태 갱신. 한 종목당 1회만 호출한다."""
    sig, stk, price = c["sig"], c["stk_cd"], c["price"]
    sized = {**sig, "_qty": c["shares"], "_price": price}
    logger.info("매수 집행 [%s] %d주 @%d (%s)", stk, c["shares"], price, reason)
    try:
        signal_repo.update_status(sig["id"], "executing")
        resp = engine.execute_buy(trade_date, sized, dmst_stex_tp=exchange)
        signal_repo.update_status(sig["id"], "done" if resp else "skipped")
    except Exception as e:
        logger.error("시그널 %s 집행 실패: %s", sig["id"], e)
        signal_repo.update_status(sig["id"], "rejected", note=str(e))
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
    logger.info("매수 집행 시작 [%s] 거래소=%s 윈도우 %02d:%02d~%02d:%02d 눌림 -%.2f%% (거래일 %s)",
                args.venue.upper(), cfg["exchange"], *cfg["start"], *cfg["deadline"],
                BUY_PULLBACK_PCT, trade_date)

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
        time.sleep(POLL_SEC)
    else:
        logger.info("closing_bet 갱신 시그널 감지 — 매수 폴링 시작")

    signals = signal_repo.get_pending_signals(trade_date)
    if not signals:
        logger.info("집행 대기 시그널 없음 — 종료")
        return 0

    block = blocklist_repo.get_codes()
    engine = ExecutionEngine()
    want_nxt = args.venue == "nxt"

    # 1) 전체 pending 후보의 거래소·점수 분류 (blocklist 제외)
    #    다른 거래소 몫의 현금을 예약하려면 전체 점수합이 필요하다.
    classified = []  # (sig, stk, score, is_nxt)
    for sig in signals:
        stk = sig["stk_cd"]
        if stk in block:
            logger.info("blocklist 제외 — signal %s [%s]", sig["id"], stk)
            signal_repo.update_status(sig["id"], "skipped", note="blocklist")
            continue
        classified.append((sig, stk, max(float(sig.get("score") or 0), 0),
                           engine.data.is_nxt_enabled(stk)))
    if not classified:
        logger.info("대상 시그널 없음 — 종료")
        return 0

    total_score = sum(s for _, _, s, _ in classified)
    venue_items = [(sig, stk, score) for (sig, stk, score, isn) in classified if isn == want_nxt]
    if not venue_items:
        logger.info("이 거래소 대상 시그널 없음 — 종료")
        return 0
    venue_score = sum(s for _, _, s in venue_items)

    # 2) 시드 = 가용현금의 점수비례 몫 (다른 거래소 몫은 예약, 해당 시간대에 집행)
    #    현금주문가능금액(100stk_ord_alow_amt)을 쓴다 — 종가베팅은 당일 매도대금을
    #    종가에 재투입하므로 미정산 매도분을 제외하는 ord_alow_amt 는 시드를 과소산정한다.
    cash = to_int(engine.client.get_deposit().get("100stk_ord_alow_amt"))
    seed = int(cash * venue_score / total_score) if total_score > 0 else 0
    logger.info("가용현금 %d × (거래소점수 %.0f / 전체 %.0f) → 시드 %d원, 후보 %d종목",
                cash, venue_score, total_score, seed, len(venue_items))

    # 3) 윈도우 시작 시점 현재가로 시드 배분 → 종목별 매수 수량 확정 (이후 눌려도 수량 고정)
    cands: list[dict] = [
        {"sig": sig, "stk_cd": stk, "score": score,
         "price": engine.data.get_market_price(stk), "high": 0, "bought": False}
        for sig, stk, score in venue_items
    ]
    for c in cands:
        c["high"] = c["price"]  # 장중 고점 초기값 = 윈도우 시작가
    allocate(seed, cands)

    # 배분 0주는 즉시 스킵 처리
    for c in cands:
        if c["shares"] < 1:
            logger.info("배분 0주 스킵 [%s] (점수 %.1f, 현재가 %d)", c["stk_cd"], c["score"], c["price"])
            signal_repo.update_status(c["sig"]["id"], "skipped", note="배분 0주")
            c["bought"] = True  # 루프 대상에서 제외

    # 4) 윈도우 폴링 — 종목별 고점 추종, 고점 대비 BUY_PULLBACK_PCT% 눌리면 즉시 매수
    while _hm(datetime.now()) < cfg["deadline"]:
        for c in cands:
            if c["bought"]:
                continue
            try:
                cur = engine.data.get_market_price(c["stk_cd"])
            except Exception as e:
                logger.warning("현재가 조회 실패 [%s]: %s", c["stk_cd"], e)
                continue
            if cur <= 0:
                continue
            if cur > c["high"]:
                c["high"] = cur
            trigger = round(c["high"] * (1 - BUY_PULLBACK_PCT / 100))
            if cur <= trigger:
                c["price"] = cur  # 체결 기록용 참고가(실주문은 시장가/IOC)
                _buy_candidate(engine, trade_date, c, cfg["exchange"],
                               f"눌림 매수 현재가 {cur} <= 고점 {c['high']} -{BUY_PULLBACK_PCT}%")
        if all(c["bought"] for c in cands):
            logger.info("전 종목 매수 완료 — 데드라인 전 종료")
            break
        time.sleep(POLL_SEC)

    # 5) 데드라인 — 끝까지 안 눌린 잔여 후보는 시장가로 매수해 추세 종목 확보
    for c in cands:
        if c["bought"]:
            continue
        try:
            cur = engine.data.get_market_price(c["stk_cd"])
            if cur > 0:
                c["price"] = cur
        except Exception as e:
            logger.warning("데드라인 현재가 조회 실패 [%s]: %s", c["stk_cd"], e)
        _buy_candidate(engine, trade_date, c, cfg["exchange"], "데드라인 시장가 매수(미눌림)")

    # 6) 관리자 알림은 체결 직후 fills_sync 워커가 실체결가로 전송한다
    #    (KRX 15:31 / NXT 19:55) — 종가 단일가/IOC 체결가는 이 시점엔 아직 미확정이라 여기서 보내지 않는다.
    logger.info("매수 집행 종료 [%s]", args.venue.upper())
    return 0


if __name__ == "__main__":
    sys.exit(main())
