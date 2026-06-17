"""주문 의도/전송 기록.

멱등성 키(idempotency_key)로 cron 재실행 시 중복 주문을 방지한다.
상태 흐름: intended → sent → accepted / rejected / filled / canceled
"""
from typing import Optional

from core.db import get_db


def list_recent(limit: int = 50) -> list[dict]:
    """최근 주문 목록 (대시보드용, 최신순)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, idempotency_key, stk_cd, side, qty, price, ord_type, mode, "
            "status, kiwoom_ord_no, created_at "
            "FROM `order` ORDER BY id DESC LIMIT %s",
            (int(limit),),
        )
        return cursor.fetchall()


def list_by_date(date_dash: str) -> list[dict]:
    """해당 날짜(YYYY-MM-DD) 주문 — 일별 상세용 (생성순)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, stk_cd, side, qty, price, ord_type, mode, status, "
            "kiwoom_ord_no, created_at "
            "FROM `order` WHERE created_at >= %s AND created_at < %s + INTERVAL 1 DAY "
            "ORDER BY id",
            (date_dash, date_dash),
        )
        return cursor.fetchall()


def find_by_idempotency_key(key: str) -> Optional[dict]:
    """동일 멱등성 키 주문이 이미 있는지 확인 (중복 전송 차단)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM `order` WHERE idempotency_key = %s", (key,))
        return cursor.fetchone()


def create_intended(
    idempotency_key: str,
    signal_id: Optional[int],
    stk_cd: str,
    side: str,
    qty: int,
    price: int,
    ord_type: str,
    mode: str,
) -> int:
    """주문 의도 기록 (전송 전). 생성된 order id 반환."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO `order` "
            "(idempotency_key, signal_id, stk_cd, side, qty, price, ord_type, mode, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'intended')",
            (idempotency_key, signal_id, stk_cd, side, qty, price, ord_type, mode),
        )
        conn.commit()
        return cursor.lastrowid


def mark_sent(order_id: int, kiwoom_ord_no: Optional[str], status: str) -> None:
    """키움 전송 결과 반영."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE `order` SET kiwoom_ord_no = %s, status = %s WHERE id = %s",
            (kiwoom_ord_no, status, order_id),
        )
        conn.commit()
