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
    """포지션 수량/평단 덮어쓰기 (reconcile 보정용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO position (stk_cd, qty, avg_price) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE qty = %s, avg_price = %s",
            (stk_cd, qty, avg_price, qty, avg_price),
        )
        conn.commit()


def apply_buy_fill(stk_cd: str, qty: int, price: int) -> None:
    """매수 체결 반영 — 가중평균 평단 갱신 (read-modify-write 단일 트랜잭션)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT qty, avg_price FROM position WHERE stk_cd = %s", (stk_cd,))
        row = cursor.fetchone()
        old_qty = row["qty"] if row else 0
        old_avg = row["avg_price"] if row else 0
        new_qty = old_qty + qty
        new_avg = round((old_qty * old_avg + qty * price) / new_qty) if new_qty > 0 else 0
        cursor.execute(
            "INSERT INTO position (stk_cd, qty, avg_price) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE qty = %s, avg_price = %s",
            (stk_cd, new_qty, new_avg, new_qty, new_avg),
        )
        conn.commit()


def apply_sell_fill(stk_cd: str, qty: int, price: int) -> int:
    """매도 체결 반영 — 수량 차감 + 실현손익 누적. 실현손익(원) 반환.

    실현손익 = (체결가 - 평단) * 매도수량. 평단은 부분매도 시 유지.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT qty, avg_price, realized_pnl FROM position WHERE stk_cd = %s", (stk_cd,)
        )
        row = cursor.fetchone()
        if not row or row["qty"] <= 0:
            return 0
        sell_qty = min(qty, row["qty"])
        realized = (price - row["avg_price"]) * sell_qty
        new_qty = row["qty"] - sell_qty
        cursor.execute(
            "UPDATE position SET qty = %s, realized_pnl = realized_pnl + %s WHERE stk_cd = %s",
            (new_qty, realized, stk_cd),
        )
        conn.commit()
        return realized
