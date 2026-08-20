"""
Trading Execution API — 자동매매 집행/조회/제어 FastAPI 서버 (localhost :8002).

대시보드(trading/frontend, :3001)의 백엔드이자 수동 제어 면(킬스위치·포지션·시그널 조회).
주문 권한은 이 도메인에만 있으며, 모든 주문은 ExecutionEngine + RiskEngine 을 경유한다.
"""
import asyncio
import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import (  # noqa: F401  (import 시 루트 .env 로드)
    DB_CONFIG, TRADING_MODE, ADMIN_PASSWORD, HARD_STOP_LOSS_PCT, TRAIL_PCT,
    PRICE_STREAM_PUSH_SEC,
)
from core.logging_setup import setup_logging
from core.repository import kiwoom_token as token_repo
from core.repository import risk_state as risk_repo
from core.repository import position as position_repo
from core.repository import risk_config as risk_config_repo
from core.repository import trade_signal as signal_repo
from core.repository import order as order_repo
from core.repository import fill as fill_repo
from core.repository import audit_log
from core.repository import blocklist as blocklist_repo
from core.repository import leverage_map as leverage_map_repo
from core.repository import settle_plan as settle_plan_repo
from core.repository import edge_rule as edge_rule_repo
from core.kiwoom_data_client import KiwoomDataClient, to_int
from core.kiwoom_order_client import KiwoomOrderClient
from core.seed_allocator import allocate, conviction_from_signal
from core.ex_rights import get_next_session_ex_rights
from core.market_calendar import next_trading_day
from core.futures_gate import sector_keep_factors, effective_keep, gated_shares
from core.macro_gate import macro_keep, month_events
from core.price_stream import get_price_stream

setup_logging()
logger = logging.getLogger("TradingAPI")

# ── 인증 ──
# 세션 토큰 = sha256(ADMIN_PASSWORD). 비번을 모르면 계산 불가 → 위조 불가.
# 로그인 성공 시 이 토큰을 프론트가 httpOnly 쿠키로 보관하고 매 요청 Authorization 헤더로 전달한다.
# ADMIN_PASSWORD 미설정 시 토큰이 빈 문자열 → 모든 보호 엔드포인트가 401(fail-closed).
SESSION_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest() if ADMIN_PASSWORD else ""

# 인증 없이 접근 가능한 경로 (헬스/루트/로그인/문서).
_AUTH_EXEMPT = {"/", "/health", "/admin/login", "/docs", "/redoc", "/openapi.json"}


def require_auth(request: Request):
    """전역 의존성 — 면제 경로 외 모든 요청은 유효한 Bearer 토큰을 요구한다."""
    if request.url.path in _AUTH_EXEMPT:
        return
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth[:7].lower() == "bearer " else ""
    if not SESSION_TOKEN or token != SESSION_TOKEN:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


def _warm_market_calendar() -> None:
    """거래일 달력(XKRX) 선로드 — 실패해도 무해(첫 조회 때 다시 로드된다)."""
    try:
        next_trading_day(datetime.now().date())
    except Exception as e:
        logger.warning("거래일 달력 워밍업 실패 — 첫 조회 시점에 로드됩니다: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # XKRX 달력 첫 로드가 2.5초쯤 걸려 재시작 직후 첫 /buy-preview(권리락 조회 경유)를 그만큼
    # 늦춘다. exchange_calendars 가 인스턴스를 캐시하므로 기동 시 백그라운드로 한 번만 만들어 둔다.
    threading.Thread(target=_warm_market_calendar, daemon=True).start()
    yield


app = FastAPI(title="Trading Execution API", dependencies=[Depends(require_auth)],
              lifespan=lifespan)


# ── 요청 바디 ──
class LoginBody(BaseModel):
    password: str = ""


class KillSwitch(BaseModel):
    flag: bool
    reason: str | None = None


class RiskConfigBody(BaseModel):
    MAX_ORDERS_PER_DAY: int = 10
    MAX_NOTIONAL_PER_NAME: int = 5_000_000
    MAX_DAILY_LOSS: int = 3_000_000
    MAX_POSITIONS: int = 5
    SEED_INIT_MULT: float = 1.0  # 최초 시드 배율(0.0~1.0, 게이트 감액보다 먼저 적용)
    LEVERAGE_ENABLED: int = 0    # 레버리지 ETF 대체매수 토글(0/1)


class BlocklistItem(BaseModel):
    stk_cd: str
    reason: str | None = None


class BlocklistBody(BaseModel):
    items: list[BlocklistItem]


class LeverageItem(BaseModel):
    src_stk_cd: str
    src_stk_nm: str | None = None
    etf_stk_cd: str
    etf_stk_nm: str | None = None


class LeverageMapBody(BaseModel):
    items: list[LeverageItem]


# ── 헬스 ──
@app.get("/health")
def health():
    """DB 연결·공유 토큰·매매 모드·킬스위치 상태 점검."""
    has_token = False
    db_ok = True
    kill = None
    try:
        tok = token_repo.get_token()
        has_token = bool(tok and tok.get("access_token"))
        kill = risk_repo.get_kill_switch()
    except Exception as e:
        db_ok = False
        logger.warning("health: 점검 실패: %s", e)
    return {
        "status": "ok",
        "service": "trading",
        "db": db_ok,
        "has_token": has_token,
        "mode": TRADING_MODE,
        "kill_switch": kill,
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "Trading Execution API"}


# ── 대시보드 로그인 (비밀번호 검증) ──
@app.post("/admin/login")
def admin_login(b: LoginBody):
    """대시보드 접속 비밀번호 검증. 성공 시 세션 토큰을 발급(프론트가 httpOnly 쿠키로 보관).
    ADMIN_PASSWORD 미설정이거나 불일치면 401."""
    if ADMIN_PASSWORD and b.password == ADMIN_PASSWORD:
        return {"ok": True, "token": SESSION_TOKEN}
    raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")


# ── 조회 (대시보드) ──
@app.get("/positions")
def positions():
    """보유 포지션 + 현재가 평가(미실현손익). 현재가 조회 실패 종목은 0 처리.

    현재가는 종목별 REST 조회(정규장 외엔 NXT 여부+NXT 일봉 2콜)라 순차로 돌면 보유 종목 수만큼
    홈 화면 로딩이 늘어난다. 표시용 조회이고 종목 간 순서 의존이 없어 4개씩 동시에 조회한다.
    """
    rows = position_repo.get_open_positions()
    if rows:
        dc = KiwoomDataClient(nxt_cache=True)  # NXT 여부는 종목당 1콜
        with ThreadPoolExecutor(max_workers=4) as pool:
            prices = list(pool.map(lambda r: dc.get_display_price(r["stk_cd"]), rows))
        for p, (cur, is_nxt) in zip(rows, prices):
            p["cur_prc"] = cur
            p["is_nxt"] = is_nxt
            p["eval_amt"] = cur * p["qty"]
            p["unrealized_pnl"] = (cur - p["avg_price"]) * p["qty"] if cur else 0
    return rows


def _heartbeat_worker(hb: dict | None) -> str | None:
    """가장 최근 하트비트로부터 실제 가동 중인 pm2 워커명을 식별.
    monitor_poll → trading-monitor, buy_poll → trading-buy-{venue}."""
    if not hb:
        return None
    if hb["event"] == "monitor_poll":
        return "trading-monitor"
    if hb["event"] == "buy_poll":
        venue = (hb.get("payload") or {}).get("venue")
        return f"trading-buy-{venue}" if venue in ("krx", "nxt") else "trading-buy"
    return None


def _monitor_phase(now: datetime):
    """현재 시각이 어느 폴링 단계인지 — (phase, in_window). 평일만 가동.

    sell  = 매도 모니터(monitor 워커)   08:00~09:30
    buy_krx = KRX 종가 매수(signal_executor --venue krx)  15:10~15:20
    buy_nxt = NXT 종가 매수(signal_executor --venue nxt)  19:40~19:50
    """
    if now.weekday() >= 5:
        return None, False
    hm = (now.hour, now.minute)
    if (8, 0) <= hm <= (9, 30):
        return "sell", True
    if (15, 10) <= hm <= (15, 20):
        return "buy_krx", True
    if (19, 40) <= hm <= (19, 50):
        return "buy_nxt", True
    return None, False


@app.get("/monitor")
def monitor():
    """자동매매 폴링 모니터 상태 — '모니터' 탭 실시간 뷰.

    매도 모니터(monitor, 08:00~09:30)와 매수 집행(signal_executor, KRX 15:10 / NXT 19:40)
    워커의 가동 여부(하트비트 기준)와 함께, 보유 포지션을 스탑선(settle_plan)·하드손절가
    (평단×(1-HARD_STOP_LOSS_PCT/100))로 평가하고, 폴링 활동 로그(매도 스탑·매수 집행)와
    최근 주문 로그를 묶어 반환한다.
    """
    now = datetime.now()
    today_dash = now.strftime("%Y-%m-%d")  # 모니터 탭은 주문·활동 로그 모두 오늘만
    phase, in_window = _monitor_phase(now)
    # 하트비트(monitor_poll/buy_poll)가 60초(=4×폴링) 안에 있으면 워커가 실제로 돌고 있다고 본다.
    hb = audit_log.last_heartbeat()
    last_poll = hb["created_at"] if hb else None
    active = bool(last_poll and (now - last_poll).total_seconds() <= 60)
    worker = _heartbeat_worker(hb) if active else None  # 실제 폴링 중인 워커 (꺼졌으면 None)

    positions = position_repo.get_open_positions()
    plans = {p["stk_cd"]: p for p in settle_plan_repo.get_active_plans()}
    if positions:
        dc = KiwoomDataClient()
        # 모니터 탭 SSE 가 살아 있으면 그 WS 스냅샷을 쓴다(REST 중복 조회 생략 + 두 경로 값 일치).
        live = get_price_stream().fresh_prices()
        for p in positions:
            hit = live.get(p["stk_cd"])
            cur, is_nxt = ((hit["prc"], hit["is_nxt"]) if hit
                           else dc.get_display_price(p["stk_cd"]))
            p["cur_prc"] = cur
            p["is_nxt"] = is_nxt
            p["eval_amt"] = cur * p["qty"]
            p["unrealized_pnl"] = (cur - p["avg_price"]) * p["qty"] if cur else 0
            # 손절가: 평단 대비 -HARD_STOP_LOSS_PCT% (plan 유무 무관 안전망)
            p["hard_stop"] = round(p["avg_price"] * (1 - HARD_STOP_LOSS_PCT / 100))
            plan = plans.get(p["stk_cd"])
            # 스탑선: 활성 청산계획의 stop_price (트레일링으로 상향됨). 장 시작 전이면 None.
            p["stop_price"] = plan["stop_price"] if plan else None
            p["plan_active"] = bool(plan)

    return {
        "active": active,
        "in_window": in_window,
        "phase": phase,
        "worker": worker,
        "last_poll_at": last_poll.isoformat() if last_poll else None,
        "poll_sec": 15,
        "hard_stop_pct": HARD_STOP_LOSS_PCT,
        "trail_pct": TRAIL_PCT,
        "positions": positions,
        # 주문 로그·활동 로그 모두 오늘 날짜만 (최신순) — 모니터 탭은 당일 폴링 활동을 본다
        "orders": list(reversed(order_repo.list_by_date(today_dash))),
        "events": audit_log.list_activity_events(50, date_dash=today_dash),
    }


@app.get("/monitor/stream")
async def monitor_stream(request: Request):
    """모니터 탭 실시간 시세 SSE — 매도 워커와 **같은 키움 WS 틱**을 대시보드로 밀어 준다.

    `core/price_stream.PriceStream` 이 조립한 스냅샷을 `PRICE_STREAM_PUSH_SEC`(1초)마다,
    바뀐 것이 있을 때만 보낸다(`data: {"seq":..,"prices":{코드:{prc,is_nxt,src,age}},"ws":{..}}`).
    보내는 것은 **가격뿐**이다 — 스탑선·활동 로그·주문은 15초 `/monitor` 폴링이 계속 담당한다
    (표시 전용 스트림이 자금 경로 상태의 출처가 되지 않게).

    ⚠️ WS 세션은 **구독자가 있을 때만** 살아 있다(§price_stream 설계 1). 스트림이 죽거나
    `PRICE_STREAM_ENABLED=0` 이면 첫 이벤트로 `{"disabled":true}` 를 보내고 닫는다 →
    프론트는 종전 15초 폴링만으로 동작한다.
    """
    stream = get_price_stream()

    async def gen():
        if not stream.acquire():
            yield 'data: {"disabled": true}\n\n'
            return
        try:
            last_seq = 0   # 프로듀서 첫 스냅샷은 seq=1 — 기동 전 빈 스냅샷(seq=0)은 보내지 않는다
            since_ping = 0.0
            while not await request.is_disconnected():
                snap = stream.snapshot()
                if snap.get("seq") != last_seq:
                    last_seq = snap.get("seq")
                    since_ping = 0.0
                    yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
                else:
                    since_ping += PRICE_STREAM_PUSH_SEC
                    if since_ping >= 15:  # 프록시·브라우저가 유휴 연결을 끊지 않게
                        since_ping = 0.0
                        yield ": ping\n\n"
                await asyncio.sleep(PRICE_STREAM_PUSH_SEC)
        finally:
            stream.release()  # 클라이언트 이탈(취소)에도 반드시 반납 → 구독자 0 이면 WS 종료

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    })


@app.get("/names")
def names():
    """종목코드 → 종목명 맵 (표시용).

    시그널에 등장한 종목명 + 레버리지 ETF 치환분(포지션/주문에만 등장해 시그널엔 없음).
    치환 매수분은 원종목만 시그널에 남으므로 ETF 이름을 여기서 합쳐 코드 노출을 막는다.
    """
    m = signal_repo.get_name_map()
    for info in leverage_map_repo.get_active_map().values():
        if info.get("etf_nm"):
            m[info["etf_cd"]] = info["etf_nm"]
    return m


@app.get("/signals")
def signals(date: str | None = None):
    """거래일 시그널 목록 (기본: 오늘)."""
    trade_date = date or datetime.now().strftime("%Y%m%d")
    return signal_repo.get_signals_by_date(trade_date)


# 선물 게이트 축 → 표시 이름. 코스피 축은 거래소별 이름(주간/야간선물)이라 진단값을 쓴다.
_AXIS_LABELS = {"nq": "나스닥선물", "us_semis": "미 프리마켓 반도체", "us_korea": "미 프리마켓 한국물"}


def _keep_reason(stk_cd: str, futures_diag: dict | None, macro_diag: dict, m_keep: float,
                 pre_shares: int, shares: int) -> str:
    """감액 keep(<1.0)이 어떤 축에서 왔는지 한 줄 설명 — 대시보드 hover/펼침 표시용.

    '게이트 감액'이라는 라벨만으로는 어느 게이트·어느 축이 얼마나 깎았는지 알 수 없어서,
    하락 축(강도>0)과 섹터 keep, 그리고 반올림 후 실제 수량 변화를 함께 적는다.
    """
    parts = []
    fd = futures_diag or {}
    det = (fd.get("detail") or {}).get(stk_cd) or {}
    axes = fd.get("axes") or {}
    downs = [
        f"{_AXIS_LABELS.get(k) or fd.get('kospi_label') or k} {a['pct']:+.2f}%"
        f"(강도 {a.get('intensity')})"
        for k, a in axes.items() if (a.get("intensity") or 0) > 0 and a.get("pct") is not None
    ]
    if downs:
        parts.append(f"선물 게이트 · {det.get('sector') or '섹터 미분류'}"
                     f"({det.get('class')}) keep {det.get('keep')} ← " + " · ".join(downs))
    if m_keep < 1.0:
        sev3 = "·".join(e["name"] for e in (macro_diag.get("events") or [])
                        if (e.get("severity") or 0) >= 3)
        parts.append(f"거시 이벤트 게이트 keep {m_keep}" + (f" ← {sev3}" if sev3 else ""))
    if not parts:
        return ""
    parts.append("배분 0주 — 단가가 배분액보다 커서(게이트 무관)" if pre_shares < 1
                 else f"배분 {pre_shares}주 → {shares}주"
                 + ("(반올림으로 수량 유지)" if pre_shares == shares else ""))
    return " / ".join(parts)


@app.get("/buy-preview")
def buy_preview(date: str | None = None):
    """오늘 매수 예정 종목 미리보기 (KRX/NXT 거래소별 시드 배분·예상 수량).

    pending 시그널을 NXT 상장 여부로 KRX(15:10~15:20)/NXT(19:40~19:50) 윈도우에 나누고,
    가용현금(100stk_ord_alow_amt)을 거래소 점수비례로 분할해 seed_allocator 로 종목별 예상
    수량을 계산한다. signal_executor 와 동일 로직이지만 **읽기 전용** — DB/주문은 건드리지 않는다.
    가격·현금·NXT 여부는 호출 시점의 실시간 값이라 실제 집행 결과와 다를 수 있다(미리보기).

    데드라인이 지난 거래소는 `closed=True` 로 표시하고 수량 0 으로 둔다 — 그 윈도우는 오늘 다시
    열리지 않으므로 '매수 예정'이 아니다(2026-08-05 GS건설: KRX 전용 종목이 16:00 회차에 후보로
    새로 올라와 15:20 데드라인을 이미 넘겼는데 계속 매수 예정으로 표시됐다).
    """
    trade_date = date or datetime.now().strftime("%Y%m%d")
    signals = signal_repo.get_pending_signals(trade_date)
    block = blocklist_repo.get_codes()
    # 권리락 스킵도 executor 와 같이 반영한다 — 신호는 19:40 집행 전까지 pending 으로 남아 있어서
    # 여기서 빼지 않으면 "안 살 종목이 매수 예정에 뜬다"(권리락 종목 사례).
    ex_rights = get_next_session_ex_rights()
    # 레버리지 대체매수 — 대시보드는 실제 매수 대상인 ETF 로 미리보기 표시(executor 와 동일 치환).
    lev_map = (leverage_map_repo.get_active_map()
               if risk_config_repo.get_risk_config().get("LEVERAGE_ENABLED", 0) else {})

    # 1) blocklist·권리락 제외 + 레버리지 치환 (조회 없음)
    targets = []
    for sig in signals:
        stk = sig["stk_cd"]
        if stk in block or stk in ex_rights:
            continue
        m = lev_map.get(stk)
        if m and m.get("etf_cd"):
            sig = {**sig, "stk_cd": m["etf_cd"], "stk_nm": m.get("etf_nm") or m["etf_cd"]}
        targets.append(sig)

    # 2) 거래소·현재가 분류 (executor 와 동일 판정) — 종목별 병렬 조회.
    #    종목당 REST 2콜(콜당 0.17s, 대부분 키움 서버 스로틀 대기)이라 순차로 돌면 9종목에 3~5초가
    #    걸려 대시보드 첫 로딩을 통째로 붙잡는다. 읽기 전용이고 종목 간 순서 의존이 없어 동시에 4개씩
    #    조회한다(키움 데이터 서버에 걸는 부하 상한 — 같은 창에서 signal_executor 도 조회한다).
    dc = KiwoomDataClient(nxt_cache=True)  # NXT 여부는 종목당 1콜 (현재가 조회 내부에서도 쓴다)

    def _classify(sig: dict) -> dict:
        stk = sig["stk_cd"]
        try:
            is_nxt = dc.is_nxt_enabled(stk)  # 먼저 조회해 캐시를 채운다(아래 현재가 조회가 재사용)
        except Exception as e:
            logger.warning("buy-preview NXT 여부 조회 실패 [%s]: %s", stk, e)
            is_nxt = False
        try:
            price = dc.get_market_price(stk)
        except Exception as e:
            logger.warning("buy-preview 현재가 조회 실패 [%s]: %s", stk, e)
            price = 0
        return {
            "sig": sig,
            "score": max(float(sig.get("score") or 0), 0),
            "price": price,
            "is_nxt": is_nxt,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        classified = list(pool.map(_classify, targets))  # 입력 순서 유지

    total_score = sum(c["score"] for c in classified)
    try:
        cash = to_int(KiwoomOrderClient().get_deposit().get("100stk_ord_alow_amt"))
    except Exception as e:
        logger.warning("buy-preview 가용현금 조회 실패: %s", e)
        cash = 0

    # 확신도(선정 근거 수) — executor 와 동일하게 계산해 미리보기 수량이 실집행과 어긋나지 않게 한다.
    try:
        score_top_n = edge_rule_repo.get_selected_count(datetime.now().strftime("%Y-%m-%d"))
    except Exception as e:
        logger.warning("buy-preview 선정 종목 수 조회 실패 — 확신도에서 점수 표 제외: %s", e)
        score_top_n = None
    for c in classified:
        c["conviction"] = conviction_from_signal(c["sig"], score_top_n)

    # 최초 시드 배율 — base 시드에 곱해 게이트 감액보다 먼저 적용(executor 와 동일, 대시보드 설정).
    seed_init_mult = risk_config_repo.get_risk_config().get("SEED_INIT_MULT", 1.0)

    # 거시 이벤트 게이트 — 보유 창의 sev3 예정 이벤트(FOMC·CPI·고용) keep. 두 거래소 공통(executor 와 동일).
    m_keep, macro_diag = macro_keep("preview")

    # 3) 거래소별 시드 = 가용현금 × (거래소 점수합 / 전체 점수합), 그 안에서 확신도 비례 배분
    #    executor 와 동일하게 게이트를 반영한다: 배분 뒤 선물(섹터별)×거시(공통) keep 으로 수량 감액.
    #    가격·현금·야간선물은 호출 시점 실시간값이라 실제 집행과 다를 수 있다(미리보기).
    venues = []
    now = datetime.now()
    # 창 표기는 표시용 — 실제 집행 창의 단일 소스는 signal_executor.VENUES 다(바꿀 때 같이 맞출 것).
    for exchange, want_nxt, window, deadline in (("KRX", False, "15:10~15:20", (15, 20)),
                                                 ("NXT", True, "19:40~19:50", (19, 50))):
        # 데드라인이 지난 거래소는 오늘 집행되지 않는다 — 배분·게이트 조회를 건너뛰고 '집행 불가'로 표시.
        closed = now > datetime.strptime(trade_date, "%Y%m%d").replace(hour=deadline[0],
                                                                       minute=deadline[1])
        items = [c for c in classified if c["is_nxt"] == want_nxt]
        venue_score = sum(c["score"] for c in items)
        seed = int(cash * venue_score / total_score) if total_score > 0 else 0
        if seed_init_mult < 1.0:
            seed = int(seed * seed_init_mult)  # 최초 시드 배율(게이트 감액보다 먼저)
        cands = [{"stk_cd": c["sig"]["stk_cd"], "score": c["score"], "price": c["price"],
                  "conviction": c["conviction"]} for c in items]
        factors, futures_diag = {}, None
        if not closed:
            allocate(seed, cands)
            # 선물 섹터 게이트 — 배분 뒤 섹터별 keep 으로 수량 감액(집행과 동일). 코스피 축은 거래소별
            #   (KRX=주간선물 / NXT=야간선물). 지표 취득 전(예: 야간선물 개장 전)이면 미개입.
            factors, futures_diag = sector_keep_factors(exchange.lower(),
                                                        [c["sig"]["stk_cd"] for c in items])

        stocks = []
        for c, a in zip(items, cands):
            sig = c["sig"]
            shares, cost = a.get("shares", 0), a.get("cost", 0)
            pre_shares = shares  # 게이트 전 배분 수량 — 0주의 원인이 게이트인지 시드인지 구분용
            # 선물(섹터별) × 거시(공통) 곱에 결합 하한 반영 (executor 와 동일)
            keep = 1.0 if closed else effective_keep(factors.get(sig["stk_cd"], 1.0) * m_keep)
            if keep < 1.0:
                shares = gated_shares(shares, keep)  # 반올림 감액(mild 컷이 1주를 0으로 안 만듦)
                cost = shares * c["price"]
            note = ("윈도우 종료" if closed
                    else "현재가 없음" if c["price"] <= 0
                    # 게이트가 실제로 수량을 0 으로 만든 경우만 게이트 탓. 배분 자체가 0주였으면
                    # (단가 > 배분액) keep<1 이어도 원인은 시드 부족이다.
                    else "게이트 감액" if shares < 1 and pre_shares >= 1
                    else "배분 0주(시드 부족)" if shares < 1
                    else None)
            stocks.append({
                "stk_cd": sig["stk_cd"],
                "stk_nm": sig.get("stk_nm"),
                "rank_no": sig.get("rank_no"),
                "score": c["score"],
                "price": c["price"],
                "shares": shares,
                "cost": cost,
                # 확신도 표 수(1=근거 1개=등가중). 2 이상이면 그만큼 비중을 더 실은 종목이다.
                "conviction": c["conviction"],
                "rule_names": sig.get("rule_names") or None,
                "keep": round(keep, 3) if keep < 1.0 else None,
                # 감액 keep 의 출처(하락 축·섹터 keep·수량 변화) — 대시보드가 hover/펼침으로 보여준다.
                "keep_reason": (_keep_reason(sig["stk_cd"], futures_diag, macro_diag, m_keep,
                                             pre_shares, shares) or None)
                if keep < 1.0 else None,
                "note": note,
            })
        stocks.sort(key=lambda s: (s["rank_no"] is None, s["rank_no"] or 0))
        venues.append({
            "exchange": exchange,
            "window": window,
            # 이 거래소 데드라인이 지났다 = 오늘 집행 없음(수량 0). 남은 pending 은 다음 회차에 정리된다.
            "closed": closed,
            "seed": 0 if closed else seed,
            "invested": sum(s["cost"] for s in stocks),
            "count": sum(1 for s in stocks if s["shares"] >= 1),
            "futures": futures_diag,
            "stocks": stocks,
        })

    macro = {"keep": m_keep, **macro_diag}
    return {"trade_date": trade_date, "cash": cash, "total_score": total_score,
            "macro": macro, "venues": venues}


def _attach_reason(rows: list[dict]) -> list[dict]:
    """미체결(체결 안 된) 주문에 '왜 안 됐나' 사유를 붙인다(거래내역 탭 표시용).
    거부는 키움 메시지(audit_log), 그 외는 상태 기반 일반 사유. 체결분은 None."""
    rejected_ids = [r["id"] for r in rows if r.get("status") == "rejected"]
    reasons = audit_log.reject_reasons_by_order_ids(rejected_ids)
    labels = {"canceled": "미체결 취소", "sent": "미체결", "accepted": "미체결",
              "intended": "전송 안 됨"}
    for r in rows:
        st = r.get("status")
        if st == "rejected":
            r["reason"] = reasons.get(r["id"]) or "주문 거부"
        elif st == "filled":
            r["reason"] = None
        else:
            r["reason"] = labels.get(st)
    return rows


@app.get("/orders")
def orders(limit: int = 50, month: str | None = None):
    """주문 목록. month=YYYYMM 이면 그 달 전체(최신순), 아니면 최근 limit 건.
    미체결엔 reason 을 실어 거래내역 탭이 표시한다. month 조회는 주문 행이 없는
    매수 스킵/차단(배분 0주·블록리스트·리스크 차단·주문가능액 부족)도 함께 섞어 시간순 정렬한다."""
    if not month:
        return _attach_reason(order_repo.list_recent(limit))
    rows = _attach_reason(order_repo.list_by_month(month)) + audit_log.buy_skips_by_month(month)
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows


@app.get("/audit")
def audit(limit: int = 50):
    """최근 감사 이벤트."""
    return audit_log.list_recent(limit)


def _trade_window(start: str, end: str) -> tuple[str, str]:
    """한 매매 사이클 시각 구간 (YYYYMMDDHHMMSS, 포함). 매수날≠매도날이면 매수날 15:00~매도날 10:00.
    종가베팅은 오후(15:10 KRX/19:40 NXT) 매수·오전(08:05 NXT/09:05 KRX) 청산이라 이 구간이 한
    사이클(매수→청산)을 딱 감싼다. 같은 종목을 여러 날 매매해도 인접 사이클이 섞이지 않는다.
    (이 구간 밖엔 종목별 감사 이벤트가 없어 로그도 동일하다.) 같은 날이면 그 날 전체."""
    if start == end:
        return f"{start}000000", f"{end}235959"
    return f"{start}150000", f"{end}100000"


def _to_dt(ts: str) -> str:
    """YYYYMMDDHHMMSS → 'YYYY-MM-DD HH:MM:SS' (SQL 비교용)."""
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"


def _effective_start(stk_cd: str, start: str, end: str) -> str:
    """모달 구간의 시작일(YYYYMMDD) 보정. 보통은 매수일(start)이지만, 매수일~매도일 사이에 이미
    이 종목 매도가 있었으면(1회 매수를 여러 날 나눠 판 분할/이월 청산) 이번 매도는 다음 사이클이라
    매도 당일(end)만 본다 — 원매수일까지 거슬러 올라가 이전 청산이 섞이지 않게 한다.
    (주말/공휴일을 끼고 다음날 청산하는 정상 사이클은 중간 매도가 없어 그대로 매수일부터 본다.)"""
    if start == end:
        return start
    sdash = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    edash = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    # 하한은 매수일 오후 15:00 — 매수(오후) 뒤에 청산이 또 있었을 때만 '연속 청산'으로 본다.
    # (매수 전 그날 오전의 다른 사이클 청산은 제외해야 매수일이 잘못 당겨지지 않는다.)
    return end if audit_log.has_sell_between(stk_cd, f"{sdash} 15:00:00", edash) else start


@app.get("/stock-events")
def stock_events(stk_cd: str, start: str, end: str | None = None):
    """한 종목의 매매 트레일(감사 이벤트, 시간순) — 청산 종목 클릭 시 워커 로그 모달용.
    start/end = YYYYMMDD (end 생략 시 start 당일). 종가베팅은 전일 매수→당일 매도라
    start=매수일·end=매도일 로 호출한다. 한 매매 사이클(매수날 15시~매도날 10시)만 본다."""
    end = end or start
    start = _effective_start(stk_cd, start, end)
    lo, hi = _trade_window(start, end)
    return audit_log.list_by_stock(stk_cd, _to_dt(lo), _to_dt(hi))


@app.get("/stock-chart")
def stock_chart(stk_cd: str, start: str, end: str | None = None):
    """1분봉 캔들 — 매수날 15:00 ~ 매도날 10:00 구간(워커 로그 모달 차트용).
    NXT(넥스트레이드)와 KRX(정규장) 분봉을 한 시계열로 합친다 — KRX 정규장(09:00~15:30) 시간대는
    KRX 봉이 우선, 그 밖(NXT 프리/애프터마켓: 오후 매수·시초가 청산)은 NXT 봉. NXT 미지원 종목은
    KRX 만. start/end = YYYYMMDD. 조회 실패/데이터 없음이면 빈 배열(차트는 '데이터 없음'으로 처리)."""
    end = end or start
    start = _effective_start(stk_cd, start, end)
    lo, hi = _trade_window(start, end)
    dc = KiwoomDataClient()
    # NXT 먼저 채우고 KRX 로 정규장 겹치는 분(minute)을 덮어쓴다(주 보드=KRX 우선, 연장시간대=NXT).
    codes = [stk_cd]
    try:
        if dc.is_nxt_enabled(stk_cd):
            codes = [f"{stk_cd}_NX", stk_cd]
    except Exception as e:  # noqa: BLE001
        logger.warning("NXT 여부 조회 실패 [%s]: %s", stk_cd, e)
    bars: dict[str, dict] = {}  # YYYYMMDDHHMM → 캔들 (분 단위 중복 제거 + 정렬 키)
    for code in codes:
        try:
            raw = dc.get_minute_chart_pages(code, tic_scope="1", base_dt=end, max_pages=2)
        except Exception as e:  # noqa: BLE001 — 차트는 부가 정보라 실패해도 모달은 떠야 한다
            logger.warning("분봉 조회 실패 [%s]: %s", code, e)
            continue
        for it in raw or []:
            tm = it.get("cntr_tm", "")
            if len(tm) < 12 or not (lo <= tm <= hi):
                continue
            bars[tm[:12]] = {
                "time": f"{tm[:4]}-{tm[4:6]}-{tm[6:8]}T{tm[8:10]}:{tm[10:12]}",
                "open": abs(to_int(it.get("open_pric"))),
                "high": abs(to_int(it.get("high_pric"))),
                "low": abs(to_int(it.get("low_pric"))),
                "close": abs(to_int(it.get("cur_prc"))),
                "volume": abs(to_int(it.get("trde_qty"))),
            }
    return [bars[k] for k in sorted(bars)]


@app.get("/pnl/monthly")
def pnl_monthly(month: str | None = None):
    """월별 일자 실현손익 — 달력용. month=YYYYMM (기본 이번 달)."""
    month = month or datetime.now().strftime("%Y%m")
    rows = risk_repo.get_month(month)
    days = {
        r["trade_date"]: {
            "realized_pnl": r["realized_pnl"] or 0,
            "orders_count": r["orders_count"] or 0,
            "breaker": bool(r["breaker_tripped"]),
        }
        for r in rows
    }
    total = sum(d["realized_pnl"] for d in days.values())
    return {"month": month, "total": total, "days": days}


@app.get("/macro-events")
def macro_events(month: str | None = None):
    """월별 거시 이벤트(macro_event 캘린더) — 손익 달력 마커용. month=YYYYMM (기본 이번 달).

    조회 실패는 빈 목록(달력은 이벤트 없이도 동작해야 한다 — 게이트의 미개입 원칙과 동형).
    """
    month = month or datetime.now().strftime("%Y%m")
    try:
        return {"month": month, "events": month_events(month)}
    except Exception as e:
        logger.warning("macro-events 조회 실패(빈 목록 반환): %s", e)
        return {"month": month, "events": []}


def _build_roundtrips(date_dash: str, sells: list[dict], realized_map: dict) -> list[dict]:
    """매도일(date_dash)의 매도를 직전 매수와 짝지어 종목별 라운드트립으로 만든다.

    종가베팅은 전일 매수 → 당일 매도라, 당일 매도를 '얼마에 사서(직전 매수가) 얼마에 팔았고
    (당일 매도가) 얼마 벌었는지(실현손익)' 한 줄로 보여주기 위한 집계. 실현손익(realized)은
    감사로그 기준의 권위값이고, 매수가·매도가는 체결가(미체결이면 참조가) 표시값이다.
    """
    prior_buys = order_repo.latest_buys_before(date_dash)
    # 수동 매수(NXT 한도초과분 → manual_buy_link, order 테이블에 없음)도 매수처 후보로 합친다.
    # 종목별로 더 최근 매수(주문 vs 수동)를 채택 — 안 그러면 그 매도가 엉뚱한 옛 매수에 묶인다.
    for cd, m in audit_log.latest_manual_buys_before(date_dash).items():
        o = prior_buys.get(cd)
        if not o or m["created_at"] >= o["created_at"]:
            prior_buys[cd] = m
    agg: dict[str, dict] = {}  # 종목별 매도 수량/금액(=Σ 체결수량*체결가)
    for o in sells:
        cd = o["stk_cd"]
        qty = o["filled_qty"] or 0   # 실제 체결분만 — 취소·미체결 주문은 청산 수량/금액에 넣지 않는다
        if qty <= 0:                 # (취소된 IOC 재시도가 주문수량으로 폴백돼 청산 수량이 부풀던 버그 수정)
            continue
        px = o["fill_price"] or o["price"]
        a = agg.setdefault(cd, {"qty": 0, "amount": 0})
        a["qty"] += qty
        a["amount"] += qty * px
    trips = []
    for cd, a in agg.items():
        sell_qty = a["qty"]
        sell_price = round(a["amount"] / sell_qty) if sell_qty else 0
        b = prior_buys.get(cd)
        buy_price = (b["fill_price"] or b["price"]) if b else 0
        bdt = b["created_at"] if b else None
        trips.append({
            "stk_cd": cd,
            "buy_date": bdt.strftime("%Y%m%d") if hasattr(bdt, "strftime") else (str(bdt)[:10].replace("-", "") or None),
            "buy_qty": (b["filled_qty"] or b["qty"]) if b else 0,
            "buy_price": buy_price or 0,
            "sell_qty": sell_qty,
            "sell_price": sell_price,
            "realized": realized_map.get(cd, 0),
        })
    # 실현손익 큰 순(이익 위 → 손실 아래)으로 정렬해 한눈에 보이게 한다.
    trips.sort(key=lambda t: t["realized"], reverse=True)
    return trips


@app.get("/day")
def day_detail(date: str | None = None):
    """일별 상세 — 매수/매도/갭여부/실현손익 + 라운드트립(매수가→매도가). date=YYYYMMDD (기본 오늘)."""
    d = date or datetime.now().strftime("%Y%m%d")
    dash = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    orders = order_repo.list_by_date(dash)
    realized_map = audit_log.realized_by_date(dash)
    plans = {p["stk_cd"]: p for p in settle_plan_repo.get_by_date(d)}
    state = risk_repo.get_state(d) or {}
    sells = [o for o in orders if o["side"] == "sell"]
    roundtrips = _build_roundtrips(dash, sells, realized_map)  # 매수가→매도가→실현손익
    # 청산 원금 = 오늘 판 수량의 매수원금 합(Σ 매수가×매도수량). 실현손익의 분모(수익률 기준).
    invested = sum(t["buy_price"] * t["sell_qty"] for t in roundtrips)
    fees = fill_repo.fees_by_date(dash)       # 당일 체결 수수료·세금(원). 실현손익은 이미 차감된 순액.
    return {
        "date": d,
        "realized_pnl": state.get("realized_pnl") or 0,
        "orders_count": state.get("orders_count") or 0,
        "buys": [o for o in orders if o["side"] == "buy" and (o.get("filled_qty") or 0) > 0],
        "sells": sells,
        "plans": list(plans.values()),       # 갭상승/하락 여부
        "realized_by_stock": realized_map,    # 종목별 실현손익
        "roundtrips": roundtrips,
        "invested": invested,                 # 오늘 청산 원금(수익률 분모)
        "fees": fees,                         # {cmsn, tax, total} — 당일 수수료·세금
    }


@app.get("/summary")
def summary(date: str | None = None):
    """일일 요약 — 실현손익·주문수·서킷브레이커·보유종목수·킬스위치."""
    trade_date = date or datetime.now().strftime("%Y%m%d")
    state = risk_repo.get_state(trade_date) or {}
    dash = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
    return {
        "trade_date": trade_date,
        "realized_pnl": state.get("realized_pnl") or 0,
        "orders_count": state.get("orders_count") or 0,
        "breaker_tripped": bool(state.get("breaker_tripped")),
        "open_positions": len(position_repo.get_open_positions()),
        "kill_switch": risk_repo.get_kill_switch(),
        "fees": fill_repo.fees_by_date(dash),   # {cmsn, tax, total} — 당일 수수료·세금
    }


# ── 리스크 설정 (대시보드에서 조회/수정) ──
@app.get("/risk-config", response_model=RiskConfigBody)
def get_risk_config():
    """현재 리스크 한도 설정."""
    return risk_config_repo.get_risk_config()


@app.put("/risk-config", response_model=RiskConfigBody)
def put_risk_config(b: RiskConfigBody):
    """리스크 한도 설정 수정. 다음 RiskEngine 생성 시점부터 적용."""
    return risk_config_repo.update_risk_config(b.model_dump())


# ── 매수 제외 목록 (blocklist) ──
@app.get("/blocklist")
def get_blocklist():
    """매수 제외 종목 목록."""
    return blocklist_repo.get_all()


@app.put("/blocklist")
def put_blocklist(b: BlocklistBody):
    """매수 제외 목록 전체 교체. 다음 매수 집행부터 적용."""
    return blocklist_repo.replace_all([i.model_dump() for i in b.items])


# ── 레버리지 ETF 대체매수 매핑 ──
@app.get("/leverage-map")
def get_leverage_map():
    """레버리지 ETF 대체매수 매핑 목록(원종목→ETF)."""
    return leverage_map_repo.get_all()


@app.put("/leverage-map")
def put_leverage_map(b: LeverageMapBody):
    """매핑 전체 교체. LEVERAGE_ENABLED=1 이면 다음 매수 집행부터 치환 적용."""
    return leverage_map_repo.replace_all([i.model_dump() for i in b.items])


# ── 제어 (수동) ──
@app.post("/kill-switch")
def set_kill_switch(b: KillSwitch):
    """킬스위치 토글 — 대시보드 긴급 정지 버튼."""
    risk_repo.set_kill_switch(b.flag, b.reason)
    return {"kill_switch": b.flag, "reason": b.reason}


# TODO: GET /signals, GET /orders, GET /audit, POST /orders(수동주문) 등 추가
