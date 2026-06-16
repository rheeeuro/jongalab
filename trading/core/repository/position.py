"""보유 포지션 상태 — 평단/수량/실현·미실현 손익.

reconcile 워커가 키움 잔고(kt00018)와 대조해 drift 를 보정한다.
"""
from typing import Optional

from core.db import get_db


def get_open_positions() -> list[dict]:
    """청산되지 않은 보유 포지션."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM position WHERE qty > 0")
        return cursor.fetchall()


def get_position(stk_cd: str) -> Optional[dict]:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM position WHERE stk_cd = %s", (stk_cd,))
        return cursor.fetchone()


def upsert_position(stk_cd: str, qty: int, avg_price: int) -> None:
    """포지션 수량/평단 갱신 (체결 반영 또는 reconcile 보정)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO position (stk_cd, qty, avg_price) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE qty = %s, avg_price = %s",
            (stk_cd, qty, avg_price, qty, avg_price),
        )
        conn.commit()
