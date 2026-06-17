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


def get_month(yyyymm: str) -> list[dict]:
    """해당 월(YYYYMM) 일별 리스크 상태 — 달력 일별 실현손익용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT trade_date, realized_pnl, orders_count, breaker_tripped "
            "FROM risk_state WHERE trade_date LIKE %s ORDER BY trade_date",
            (yyyymm + "%",),
        )
        return cursor.fetchall()


def ensure_row(trade_date: str) -> None:
    """해당 거래일 행이 없으면 기본값으로 생성 (멱등)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT IGNORE INTO risk_state (trade_date) VALUES (%s)", (trade_date,)
        )
        conn.commit()


def increment_orders(trade_date: str, n: int = 1) -> None:
    """일일 주문 건수 증가 (주문 전송 성공 시 호출)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO risk_state (trade_date, orders_count) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE orders_count = orders_count + %s",
            (trade_date, n, n),
        )
        conn.commit()


def add_realized_pnl(trade_date: str, amount: int) -> None:
    """일일 실현손익 누적 (청산 체결 반영 시 호출)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO risk_state (trade_date, realized_pnl) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE realized_pnl = realized_pnl + %s",
            (trade_date, amount, amount),
        )
        conn.commit()


def set_breaker(trade_date: str, tripped: bool) -> None:
    """서킷브레이커 발동 플래그 기록 (일자별)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO risk_state (trade_date, breaker_tripped) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE breaker_tripped = %s",
            (trade_date, tripped, tripped),
        )
        conn.commit()


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
