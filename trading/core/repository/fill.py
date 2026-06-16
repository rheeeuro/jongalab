"""체결 기록 — 키움 체결 통보/조회로 갱신, 포지션 산출의 근거."""
from core.db import get_db


def record_fill(order_id: int, stk_cd: str, qty: int, price: int) -> int:
    """체결 1건 기록. 생성된 fill id 반환."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO fill (order_id, stk_cd, qty, price) VALUES (%s, %s, %s, %s)",
            (order_id, stk_cd, qty, price),
        )
        conn.commit()
        return cursor.lastrowid


def get_fills_by_order(order_id: int) -> list[dict]:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM fill WHERE order_id = %s", (order_id,))
        return cursor.fetchall()
