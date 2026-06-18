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

from core.config import DB_CONFIG, TRADING_MODE, ADMIN_PASSWORD  # noqa: F401  (import 시 루트 .env 로드)
from core.logging_setup import setup_logging
from core.repository import kiwoom_token as token_repo
from core.repository import risk_state as risk_repo
from core.repository import position as position_repo
from core.repository import risk_config as risk_config_repo
from core.repository import trade_signal as signal_repo
from core.repository import order as order_repo
from core.repository import audit_log
from core.repository import blocklist as blocklist_repo
from core.repository import settle_plan as settle_plan_repo
from core.kiwoom_data_client import KiwoomDataClient

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
            cur = dc.get_current_price(p["stk_cd"])
            p["cur_prc"] = cur
            p["eval_amt"] = cur * p["qty"]
            p["unrealized_pnl"] = (cur - p["avg_price"]) * p["qty"] if cur else 0
    return rows


@app.get("/names")
def names():
    """종목코드 → 종목명 맵 (표시용)."""
    return signal_repo.get_name_map()


@app.get("/signals")
def signals(date: str | None = None):
    """거래일 시그널 목록 (기본: 오늘)."""
    trade_date = date or datetime.now().strftime("%Y%m%d")
    return signal_repo.get_signals_by_date(trade_date)


@app.get("/orders")
def orders(limit: int = 50):
    """최근 주문 목록."""
    return order_repo.list_recent(limit)


@app.get("/audit")
def audit(limit: int = 50):
    """최근 감사 이벤트."""
    return audit_log.list_recent(limit)


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
    return {
        "date": d,
        "realized_pnl": state.get("realized_pnl") or 0,
        "orders_count": state.get("orders_count") or 0,
        "buys": [o for o in orders if o["side"] == "buy"],
        "sells": sells,
        "plans": list(plans.values()),       # 갭상승/하락 여부
        "realized_by_stock": realized_map,    # 종목별 실현손익
        "roundtrips": _build_roundtrips(dash, sells, realized_map),  # 매수가→매도가→실현손익
    }


@app.get("/summary")
def summary(date: str | None = None):
    """일일 요약 — 실현손익·주문수·서킷브레이커·보유종목수·킬스위치."""
    trade_date = date or datetime.now().strftime("%Y%m%d")
    state = risk_repo.get_state(trade_date) or {}
    return {
        "trade_date": trade_date,
        "realized_pnl": state.get("realized_pnl") or 0,
        "orders_count": state.get("orders_count") or 0,
        "breaker_tripped": bool(state.get("breaker_tripped")),
        "open_positions": len(position_repo.get_open_positions()),
        "kill_switch": risk_repo.get_kill_switch(),
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
