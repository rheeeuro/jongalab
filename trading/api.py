"""
Trading Execution API — 자동매매 집행/조회/제어 FastAPI 서버 (localhost :8002).

대시보드(trading/frontend, :3001)의 백엔드이자 수동 제어 면(킬스위치·포지션·시그널 조회).
주문 권한은 이 도메인에만 있으며, 모든 주문은 ExecutionEngine + RiskEngine 을 경유한다.
"""
import hashlib
import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel

from core.config import (  # noqa: F401  (import 시 루트 .env 로드)
    DB_CONFIG, TRADING_MODE, ADMIN_PASSWORD, HARD_STOP_LOSS_PCT, TRAIL_PCT, BUY_PULLBACK_PCT,
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
from core.repository import settle_plan as settle_plan_repo
from core.kiwoom_data_client import KiwoomDataClient, to_int
from core.kiwoom_order_client import KiwoomOrderClient
from core.seed_allocator import allocate

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


app = FastAPI(title="Trading Execution API", dependencies=[Depends(require_auth)])


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


class BlocklistItem(BaseModel):
    stk_cd: str
    reason: str | None = None


class BlocklistBody(BaseModel):
    items: list[BlocklistItem]


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
    """보유 포지션 + 현재가 평가(미실현손익). 현재가 조회 실패 종목은 0 처리."""
    rows = position_repo.get_open_positions()
    if rows:
        dc = KiwoomDataClient()
        for p in rows:
            cur, is_nxt = dc.get_display_price(p["stk_cd"])
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
    buy_krx = KRX 눌림 매수(signal_executor --venue krx)  15:00~15:20
    buy_nxt = NXT 눌림 매수(signal_executor --venue nxt)  19:30~19:50
    """
    if now.weekday() >= 5:
        return None, False
    hm = (now.hour, now.minute)
    if (8, 0) <= hm <= (9, 30):
        return "sell", True
    if (15, 0) <= hm <= (15, 20):
        return "buy_krx", True
    if (19, 30) <= hm <= (19, 50):
        return "buy_nxt", True
    return None, False


@app.get("/monitor")
def monitor():
    """자동매매 폴링 모니터 상태 — '모니터' 탭 실시간 뷰.

    매도 모니터(monitor, 08:00~09:30)와 매수 집행(signal_executor, KRX 15:00 / NXT 19:30)
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
        for p in positions:
            cur, is_nxt = dc.get_display_price(p["stk_cd"])
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
        "pullback_pct": BUY_PULLBACK_PCT,
        "positions": positions,
        # 주문 로그·활동 로그 모두 오늘 날짜만 (최신순) — 모니터 탭은 당일 폴링 활동을 본다
        "orders": list(reversed(order_repo.list_by_date(today_dash))),
        "events": audit_log.list_activity_events(50, date_dash=today_dash),
    }


@app.get("/names")
def names():
    """종목코드 → 종목명 맵 (표시용)."""
    return signal_repo.get_name_map()


@app.get("/signals")
def signals(date: str | None = None):
    """거래일 시그널 목록 (기본: 오늘)."""
    trade_date = date or datetime.now().strftime("%Y%m%d")
    return signal_repo.get_signals_by_date(trade_date)


@app.get("/buy-preview")
def buy_preview(date: str | None = None):
    """오늘 매수 예정 종목 미리보기 (KRX/NXT 거래소별 시드 배분·예상 수량).

    pending 시그널을 NXT 상장 여부로 KRX(15:00~15:20)/NXT(19:30~19:50) 윈도우에 나누고,
    가용현금(100stk_ord_alow_amt)을 거래소 점수비례로 분할해 seed_allocator 로 종목별 예상
    수량을 계산한다. signal_executor 와 동일 로직이지만 **읽기 전용** — DB/주문은 건드리지 않는다.
    가격·현금·NXT 여부는 호출 시점의 실시간 값이라 실제 집행 결과와 다를 수 있다(미리보기).
    """
    trade_date = date or datetime.now().strftime("%Y%m%d")
    signals = signal_repo.get_pending_signals(trade_date)
    block = blocklist_repo.get_codes()

    # 1) blocklist 제외 후 거래소·점수·현재가 분류 (executor 와 동일)
    dc = KiwoomDataClient()
    classified = []  # {sig, is_nxt, price}
    for sig in signals:
        stk = sig["stk_cd"]
        if stk in block:
            continue
        try:
            price = dc.get_market_price(stk)
        except Exception as e:
            logger.warning("buy-preview 현재가 조회 실패 [%s]: %s", stk, e)
            price = 0
        try:
            is_nxt = dc.is_nxt_enabled(stk)
        except Exception as e:
            logger.warning("buy-preview NXT 여부 조회 실패 [%s]: %s", stk, e)
            is_nxt = False
        classified.append({
            "sig": sig,
            "score": max(float(sig.get("score") or 0), 0),
            "price": price,
            "is_nxt": is_nxt,
        })

    total_score = sum(c["score"] for c in classified)
    try:
        cash = to_int(KiwoomOrderClient().get_deposit().get("100stk_ord_alow_amt"))
    except Exception as e:
        logger.warning("buy-preview 가용현금 조회 실패: %s", e)
        cash = 0

    # 2) 거래소별 시드 = 가용현금 × (거래소 점수합 / 전체 점수합), 그 안에서 점수가중 배분
    venues = []
    for exchange, want_nxt, window in (("KRX", False, "15:00~15:20"), ("NXT", True, "19:30~19:50")):
        items = [c for c in classified if c["is_nxt"] == want_nxt]
        venue_score = sum(c["score"] for c in items)
        seed = int(cash * venue_score / total_score) if total_score > 0 else 0
        cands = [{"stk_cd": c["sig"]["stk_cd"], "score": c["score"], "price": c["price"]} for c in items]
        allocate(seed, cands)
        stocks = []
        for c, a in zip(items, cands):
            sig = c["sig"]
            shares, cost = a.get("shares", 0), a.get("cost", 0)
            note = ("현재가 없음" if c["price"] <= 0
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
                "note": note,
            })
        stocks.sort(key=lambda s: (s["rank_no"] is None, s["rank_no"] or 0))
        venues.append({
            "exchange": exchange,
            "window": window,
            "seed": seed,
            "invested": sum(s["cost"] for s in stocks),
            "count": sum(1 for s in stocks if s["shares"] >= 1),
            "stocks": stocks,
        })

    return {"trade_date": trade_date, "cash": cash, "total_score": total_score, "venues": venues}


@app.get("/orders")
def orders(limit: int = 50, month: str | None = None):
    """주문 목록. month=YYYYMM 이면 그 달 전체(최신순), 아니면 최근 limit 건."""
    if month:
        return order_repo.list_by_month(month)
    return order_repo.list_recent(limit)


@app.get("/audit")
def audit(limit: int = 50):
    """최근 감사 이벤트."""
    return audit_log.list_recent(limit)


@app.get("/stock-events")
def stock_events(stk_cd: str, start: str, end: str | None = None):
    """한 종목의 매매 트레일(감사 이벤트, 시간순) — 청산 종목 클릭 시 워커 로그 모달용.
    start/end = YYYYMMDD (end 생략 시 start 당일). 종가베팅은 전일 매수→당일 매도라
    start=매수일·end=매도일 로 호출한다."""
    end = end or start
    sdash = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    edash = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    return audit_log.list_by_stock(stk_cd, sdash, edash)


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


def _build_roundtrips(date_dash: str, sells: list[dict], realized_map: dict) -> list[dict]:
    """매도일(date_dash)의 매도를 직전 매수와 짝지어 종목별 라운드트립으로 만든다.

    종가베팅은 전일 매수 → 당일 매도라, 당일 매도를 '얼마에 사서(직전 매수가) 얼마에 팔았고
    (당일 매도가) 얼마 벌었는지(실현손익)' 한 줄로 보여주기 위한 집계. 실현손익(realized)은
    감사로그 기준의 권위값이고, 매수가·매도가는 체결가(미체결이면 참조가) 표시값이다.
    """
    prior_buys = order_repo.latest_buys_before(date_dash)
    agg: dict[str, dict] = {}  # 종목별 매도 수량/금액(=Σ 체결수량*체결가)
    for o in sells:
        cd = o["stk_cd"]
        qty = o["filled_qty"] or o["qty"]
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


# ── 제어 (수동) ──
@app.post("/kill-switch")
def set_kill_switch(b: KillSwitch):
    """킬스위치 토글 — 대시보드 긴급 정지 버튼."""
    risk_repo.set_kill_switch(b.flag, b.reason)
    return {"kill_switch": b.flag, "reason": b.reason}


# TODO: GET /signals, GET /orders, GET /audit, POST /orders(수동주문) 등 추가
