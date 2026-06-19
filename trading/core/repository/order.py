"""주문 의도/전송 기록.

멱등성 키(idempotency_key)로 cron 재실행 시 중복 주문을 방지한다.
상태 흐름: intended → sent → accepted / rejected / filled / canceled
"""
from typing import Optional

from core.db import get_db


def list_recent(limit: int = 50) -> list[dict]:
    """최근 주문 목록 (대시보드용, 최신순).

    price 는 주문 시점 참조가(시장가/IOC 는 ord_uv=0 이라 실체결가와 다름).
    fill_price 는 실제 체결 수량가중평균가(미체결이면 NULL) → 대시보드는 이걸 우선 표시.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT o.id, o.idempotency_key, o.stk_cd, o.side, o.qty, o.price, o.ord_type, "
            "o.mode, o.status, o.kiwoom_ord_no, o.created_at, "
            "ROUND(SUM(f.qty * f.price) / NULLIF(SUM(f.qty), 0)) AS fill_price, "
            "COALESCE(SUM(f.qty), 0) AS filled_qty "
            "FROM `order` o LEFT JOIN fill f ON f.order_id = o.id "
            "GROUP BY o.id ORDER BY o.id DESC LIMIT %s",
            (int(limit),),
        )
        return cursor.fetchall()


def get_open_sent() -> list[dict]:
    """live 전송 완료(미체결 반영 전) 주문 — 체결 동기화 대상."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, stk_cd, side, qty, kiwoom_ord_no FROM `order` "
            "WHERE status = 'sent' AND mode = 'live' AND kiwoom_ord_no IS NOT NULL"
        )
        return cursor.fetchall()


def get_stale_sent() -> list[dict]:
    """전일 이전에 전송됐는데 아직 'sent'(미체결)인 주문 — 개장 시 자동취소 대상."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, stk_cd, kiwoom_ord_no FROM `order` "
            "WHERE status = 'sent' AND mode = 'live' AND kiwoom_ord_no IS NOT NULL "
            "AND created_at < CURDATE()"
        )
        return cursor.fetchall()


def mark_canceled(order_id: int) -> None:
    """주문을 취소 상태로 정리."""
    with get_db() as (conn, cursor):
        cursor.execute("UPDATE `order` SET status = 'canceled' WHERE id = %s", (order_id,))
        conn.commit()


def list_by_date(date_dash: str) -> list[dict]:
    """해당 날짜(YYYY-MM-DD) 주문 — 일별 상세용 (생성순).

    fill_price = 실제 체결 수량가중평균가(미체결 NULL). price 는 주문 시점 참조가.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT o.id, o.stk_cd, o.side, o.qty, o.price, o.ord_type, o.mode, o.status, "
            "o.kiwoom_ord_no, o.created_at, "
            "ROUND(SUM(f.qty * f.price) / NULLIF(SUM(f.qty), 0)) AS fill_price, "
            "COALESCE(SUM(f.qty), 0) AS filled_qty "
            "FROM `order` o LEFT JOIN fill f ON f.order_id = o.id "
            "WHERE o.created_at >= %s AND o.created_at < %s + INTERVAL 1 DAY "
            "GROUP BY o.id ORDER BY o.id",
            (date_dash, date_dash),
        )
        return cursor.fetchall()


def latest_buys_before(date_dash: str) -> dict:
    """각 종목의 'date_dash(YYYY-MM-DD) 0시 이전' 가장 최근 매수 1건 — 매도일 라운드트립 매칭용.

    종가베팅은 전일 매수 → 익일 아침 매도라, 매도일의 매도와 짝지을 매수는 그 날짜 직전의
    최신 매수다(주말/공휴일 간격 무관). 거부/취소/미전송은 제외.
    반환: {stk_cd: {stk_cd, qty, price, fill_price, filled_qty, created_at}} (종목당 최신 1건).
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT o.stk_cd, o.qty, o.price, o.created_at, "
            "ROUND(SUM(f.qty * f.price) / NULLIF(SUM(f.qty), 0)) AS fill_price, "
            "COALESCE(SUM(f.qty), 0) AS filled_qty "
            "FROM `order` o LEFT JOIN fill f ON f.order_id = o.id "
            "WHERE o.side = 'buy' AND o.status NOT IN ('intended', 'rejected', 'canceled') "
            "AND o.created_at < %s "
            "GROUP BY o.id ORDER BY o.id",
            (date_dash,),
        )
        rows = cursor.fetchall()
    # id 오름차순 → 같은 종목이 여러 번이면 마지막(최신)이 덮어써 종목당 최신 1건만 남는다.
    return {r["stk_cd"]: r for r in rows}


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
