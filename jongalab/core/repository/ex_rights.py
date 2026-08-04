"""권리락 예정일 캘린더(`ex_rights_schedule`) 데이터 접근 — sql/48.

disclosure_collector 가 쓰고, trading signal_executor 가 읽기 전용으로 조회해 매수를 건너뛴다
(jongalab 판단 → trading 집행 단방향. trading 쪽 조회는 `trading/core/ex_rights.py`).
"""
from datetime import date

from core.db import get_db


def save_schedules(rows: list[dict]) -> int:
    """권리락 예정 upsert. rows: [{ticker, ex_rights_date, record_date, ratio,
    listing_date, source_key, corp_name}]. 신규 삽입 행 수 반환.

    (ticker, ex_rights_date) 가 PK 라 같은 건 재수집은 멱등이다 — 일정이 **변경**되면
    새 권리락일로 행이 하나 더 생기는데, 지난 날짜 행은 조회 조건(그날 = 익일)에서
    자연히 빠지므로 무해하다(변경 이력이 남는 편이 추적에 낫다).
    """
    if not rows:
        return 0
    inserted = 0
    with get_db() as (conn, cursor):
        for r in rows:
            cursor.execute(
                """INSERT INTO ex_rights_schedule
                       (ticker, ex_rights_date, record_date, ratio, listing_date,
                        source, source_key, corp_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE record_date = VALUES(record_date),
                                           ratio = VALUES(ratio),
                                           listing_date = VALUES(listing_date),
                                           source = VALUES(source),
                                           source_key = VALUES(source_key),
                                           corp_name = VALUES(corp_name)""",
                (r["ticker"], r["ex_rights_date"], r.get("record_date"), r.get("ratio"),
                 r.get("listing_date"), r.get("source") or "dart", r["source_key"],
                 r.get("corp_name")),
            )
            if cursor.rowcount == 1:  # 1=INSERT / 2=UPDATE / 0=변경 없음
                inserted += 1
        conn.commit()
    return inserted


def get_tickers_on(ex_rights_date: date | str) -> dict[str, dict]:
    """그날 권리락인 종목 — {ticker: {ratio, record_date, corp_name}}."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT ticker, ratio, record_date, listing_date, corp_name "
            "FROM ex_rights_schedule WHERE ex_rights_date = %s",
            (ex_rights_date,),
        )
        return {r["ticker"]: r for r in cursor.fetchall()}
