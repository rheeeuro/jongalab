"""일일 리스크 상태 — 한도 소진·서킷브레이커·킬스위치 (단일행 패턴, 거래일 키).

risk_engine 이 주문 전 검사·갱신한다. kill_switch 는 env 플래그와 OR 로 합쳐 판정한다.
"""
from typing import Optional

from core.db import get_db


def get_state(trade_date: str) -> Optional[dict]:
    """해당 거래일 리스크 상태 (없으면 None → 엔진이 기본값으로 초기화)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM risk_state WHERE trade_date = %s", (trade_date,))
        return cursor.fetchone()


def get_kill_switch() -> bool:
    """DB 킬스위치 플래그 (전역, 거래일 무관)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT flag FROM kill_switch WHERE id = 1")
        row = cursor.fetchone()
        return bool(row and row.get("flag"))


def set_kill_switch(flag: bool, reason: Optional[str] = None) -> None:
    """킬스위치 토글 (대시보드/서킷브레이커가 호출)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO kill_switch (id, flag, reason) VALUES (1, %s, %s) "
            "ON DUPLICATE KEY UPDATE flag = %s, reason = %s",
            (flag, reason, flag, reason),
        )
        conn.commit()
