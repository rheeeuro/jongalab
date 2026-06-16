"""
Trading Execution API — 자동매매 집행/조회/제어 FastAPI 서버 (localhost :8002).

대시보드(trading/frontend, :3001)의 백엔드이자 수동 제어 면(킬스위치·포지션·시그널 조회).
주문 권한은 이 도메인에만 있으며, 모든 주문은 ExecutionEngine + RiskEngine 을 경유한다.
"""
import logging

from fastapi import FastAPI
from pydantic import BaseModel

from core.config import DB_CONFIG, TRADING_MODE  # noqa: F401  (import 시 루트 .env 로드)
from core.logging_setup import setup_logging
from core.repository import kiwoom_token as token_repo
from core.repository import risk_state as risk_repo
from core.repository import position as position_repo

setup_logging()
logger = logging.getLogger("TradingAPI")

app = FastAPI(title="Trading Execution API")


# ── 요청 바디 ──
class KillSwitch(BaseModel):
    flag: bool
    reason: str | None = None


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
    """보유 포지션."""
    return position_repo.get_open_positions()


# ── 제어 (수동) ──
@app.post("/kill-switch")
def set_kill_switch(b: KillSwitch):
    """킬스위치 토글 — 대시보드 긴급 정지 버튼."""
    risk_repo.set_kill_switch(b.flag, b.reason)
    return {"kill_switch": b.flag, "reason": b.reason}


# TODO: GET /signals, GET /orders, GET /audit, POST /orders(수동주문) 등 추가
