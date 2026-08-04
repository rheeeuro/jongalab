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


def list_by_month(month: str) -> list[dict]:
    """해당 월(YYYYMM) 주문 — 거래내역 월별 보기용 (최신순).

    fill_price = 실제 체결 수량가중평균가(미체결 NULL). price 는 주문 시점 참조가.
    """
    first_day = f"{month[:4]}-{month[4:6]}-01"
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT o.id, o.idempotency_key, o.stk_cd, o.side, o.qty, o.price, o.ord_type, "
            "o.mode, o.status, o.kiwoom_ord_no, o.created_at, "
            "ROUND(SUM(f.qty * f.price) / NULLIF(SUM(f.qty), 0)) AS fill_price, "
            "COALESCE(SUM(f.qty), 0) AS filled_qty "
            "FROM `order` o LEFT JOIN fill f ON f.order_id = o.id "
            "WHERE o.created_at >= %s AND o.created_at < %s + INTERVAL 1 MONTH "
            "GROUP BY o.id ORDER BY o.id DESC",
            (first_day, first_day),
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


def get_open_sent_aged(min_age_sec: int) -> list[dict]:
    """전송 후 min_age_sec 초가 지난 'sent' 주문 — '죽은 주문' 판정 대상.

    `get_open_sent`(체결 동기화용, 전체)와 달리 **갓 전송된 주문을 제외**한다. 전량체결 직후의
    주문은 미체결 목록(ka10075)엔 이미 없고 체결내역(ka10076) 반영은 몇 초 늦을 수 있어,
    그 구간에 판정하면 체결된 주문을 '소멸'로 오인한다(2026-08-05 레인보우로보틱스).
    updated_at 은 'intended'→'sent' 로 바뀐 시각 = 전송 시각이다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, stk_cd, side, qty, kiwoom_ord_no FROM `order` "
            "WHERE status = 'sent' AND mode = 'live' AND kiwoom_ord_no IS NOT NULL "
            "AND updated_at <= NOW() - INTERVAL %s SECOND",
            (int(min_age_sec),),
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


def void_dead_order(order_id: int) -> None:
    """체결 0으로 소멸한 주문(브로커에 없는 'sent') 마감 + 멱등키 해제.

    멱등키 끝에 ':dead:<id>' 를 붙여 해제하면, 같은 거래일·tag 의 재매도가 다시 가능해진다
    (find_by_idempotency_key 가 상태 무관으로 키를 찾으므로, 키 자체를 비워줘야 재시도된다).
    id 를 함께 붙여 고유성을 보장한다: 키 해제 후 같은 base 키로 재매도된 주문이 또 죽어
    재차 정리될 때, 단순히 ':dead' 만 붙이면 먼저 정리된 주문과 키가 충돌(Duplicate entry)해
    UPDATE 가 실패하고 그 주문이 'sent' 로 남아 매 폴링마다 같은 예외를 반복한다."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE `order` SET status = 'canceled', "
            "idempotency_key = CONCAT(idempotency_key, ':dead:', id) WHERE id = %s",
            (order_id,),
        )
        conn.commit()


def unvoid_dead_order(order_id: int) -> bool:
    """`void_dead_order` 오판정 되돌리기 — 'sent' 복귀 + 멱등키 원복. 되돌렸으면 True.

    죽은 주문 판정은 '브로커 미체결(ka10075)에 없음 + 로컬 체결 0' 인데, **전량체결 직후**의
    주문도 미체결 목록엔 없고 체결내역(ka10076) 반영은 몇 초 늦을 수 있다. 그 경합에 걸려
    실제로는 체결된 주문이 canceled 로 마감되면 `sync_fills`(status='sent' 만 조회)가 다시는
    보지 않아 체결·실현손익이 영구 누락되고 유령 포지션이 남는다. 이 함수로 'sent' 로 되돌리면
    다음 `sync_fills` 가 정상 경로로 체결을 반영한다(값을 손으로 써넣지 않는다).
    ':dead:<id>' 접미사를 떼어 원래 멱등키를 복원하므로 중복 매도 차단도 함께 되살아난다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE `order` SET status = 'sent', "
            "idempotency_key = REPLACE(idempotency_key, CONCAT(':dead:', id), '') "
            "WHERE id = %s AND status = 'canceled' "
            "AND idempotency_key LIKE CONCAT('%%:dead:', id)",
            (order_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


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
    """키움 전송 결과 반영.

    거부(rejected)면 멱등키 뒤에 ':x{id}' 를 붙여 유니크하게 바꿔 베이스 키를 풀어준다.
    거부된 주문은 체결되지 않았으므로(키움이 return_code≠0/주문번호 없음으로 반려)
    같은 키의 재시도는 중복 전송이 아니다. 이렇게 안 하면 거부 행이 UNIQUE 멱등키를
    영구 점유해 당일 동일 (거래일·시그널·tag) 매도/매수 재시도가 전부 차단된다
    (예: 휴장시간 stop 매도 거부 → 같은 종목 stop 재시도 불가). 거부 행 자체는
    감사 로그로 그대로 보존된다. sent/filled 등은 키를 유지해 중복 전송을 계속 막는다."""
    with get_db() as (conn, cursor):
        if status == "rejected":
            cursor.execute(
                "UPDATE `order` SET kiwoom_ord_no = %s, status = %s, "
                "idempotency_key = CONCAT(idempotency_key, ':x', id) WHERE id = %s",
                (kiwoom_ord_no, status, order_id),
            )
        else:
            cursor.execute(
                "UPDATE `order` SET kiwoom_ord_no = %s, status = %s WHERE id = %s",
                (kiwoom_ord_no, status, order_id),
            )
        conn.commit()
