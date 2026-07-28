"""사건 계층(stock_event) 데이터 접근 — DART 공시 적재·조회.

news_mention(원자료, 14일 보존)과 달리 stock_event 는 **영구 보존**한다.
정규화된 1행 = 사건 1건이라 테이블이 천천히 자라고(하루 수백 행), 익일 시초가 라벨과
조인한 이벤트 타입별 엣지 검증이 이 테이블의 존재 이유다.
"""
from datetime import date

from core.db import get_db


def save_events(rows: list[dict]) -> int:
    """공시 사건 일괄 적재. (source, source_key) 중복은 무시 → 30분 폴링 멱등.

    rows 항목: {ticker, event_date, source, source_key, event_type, direction,
                is_veto_type, is_subject, is_correction, first_seen_at, title, corp_name, raw_url}
    반환: 실제 삽입된 행 수(신규 사건 수).
    """
    if not rows:
        return 0
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT IGNORE INTO stock_event
                (ticker, event_date, source, source_key, event_type, direction,
                 is_veto_type, is_subject, is_correction, first_seen_at, title, corp_name, raw_url)
            VALUES (%(ticker)s, %(event_date)s, %(source)s, %(source_key)s, %(event_type)s,
                    %(direction)s, %(is_veto_type)s, %(is_subject)s, %(is_correction)s,
                    %(first_seen_at)s, %(title)s, %(corp_name)s, %(raw_url)s)
            """,
            rows,
        )
        inserted = cursor.rowcount
        conn.commit()
    return inserted


def get_events_by_date(event_date: date | str, tickers: list[str] | None = None) -> dict[str, list[dict]]:
    """해당 일자 사건을 {종목코드: [사건, ...]} 로. tickers 를 주면 그 종목만.

    closing_bet 이 유니버스 전체분을 한 번에 받아 disc_* 라벨을 굽는다
    (종목별 개별 조회는 후보 수만큼 왕복이 생겨 쓰지 않는다).
    """
    sql = (
        "SELECT ticker, event_type, direction, is_veto_type, is_subject, is_correction, "
        "       first_seen_at, title, raw_url "
        "FROM stock_event WHERE event_date = %s"
    )
    params: list = [event_date]
    if tickers is not None:
        if not tickers:
            return {}
        sql += " AND ticker IN (" + ",".join(["%s"] * len(tickers)) + ")"
        params.extend(tickers)
    sql += " ORDER BY first_seen_at"

    out: dict[str, list[dict]] = {}
    with get_db() as (conn, cursor):
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            out.setdefault(row["ticker"], []).append(row)
    return out


def count_by_date(event_date: date | str) -> int:
    """해당 일자 적재 건수 — 수집기 로그·수집 공백 점검용."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS c FROM stock_event WHERE event_date = %s", (event_date,))
        return int(cursor.fetchone()["c"])
