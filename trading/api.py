"""
Trading Execution API — 자동매매 집행/조회/제어 FastAPI 서버 (localhost :8002).

대시보드(trading/frontend, :3001)의 백엔드이자 수동 제어 면(킬스위치·포지션·시그널 조회).
주문 권한은 이 도메인에만 있으며, 모든 주문은 ExecutionEngine + RiskEngine 을 경유한다.
"""
import logging
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

from core.config import DB_CONFIG, TRADING_MODE  # noqa: F401  (import 시 루트 .env 로드)
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

app = FastAPI(title="Trading Execution API")


# ── 요청 바디 ──
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


@app.get("/day")
def day_detail(date: str | None = None):
    """일별 상세 — 매수/매도/갭여부/실현손익. date=YYYYMMDD (기본 오늘)."""
    d = date or datetime.now().strftime("%Y%m%d")
    dash = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    orders = order_repo.list_by_date(dash)
    realized_map = audit_log.realized_by_date(dash)
    plans = {p["stk_cd"]: p for p in settle_plan_repo.get_by_date(d)}
    state = risk_repo.get_state(d) or {}
    return {
        "date": d,
        "realized_pnl": state.get("realized_pnl") or 0,
        "orders_count": state.get("orders_count") or 0,
        "buys": [o for o in orders if o["side"] == "buy"],
        "sells": [o for o in orders if o["side"] == "sell"],
        "plans": list(plans.values()),       # 갭상승/하락 여부
        "realized_by_stock": realized_map,    # 종목별 실현손익
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
