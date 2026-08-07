"""macro_event(거시 이벤트 캘린더) 접근 — 수동 시드 일정의 고갈 감시용 조회.

캘린더 자체는 sql/18. migrate_macro_event.sql 로 수동 시드하고,
trading macro_gate 가 매수 시점에 읽기 전용으로 조회한다(이 저장소는 jongalab 워커용).
"""
from datetime import datetime

from core.db import get_db


def last_event_time(min_severity: int = 3) -> datetime | None:
    """가장 늦은 이벤트 시각 — 캘린더가 언제까지 시드돼 있는지(고갈 임박 판정용).

    기본이 severity>=3 인 이유: 실제로 시드를 감액하는 건 sev3 뿐이라(macro_gate) 고갈 감시
    대상도 그 계열이어야 한다. 전체를 보면 관찰 전용 sev2(PPI·해외 실적 등)가 더 멀리 시드돼
    있을 때 sev3 고갈을 가려버린다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT MAX(event_time) AS last_ev FROM macro_event WHERE severity >= %s",
            (int(min_severity),),
        )
        row = cursor.fetchone()
        return row["last_ev"] if row else None


def by_month(month: str) -> list[dict]:
    """해당 월(YYYY-MM)의 이벤트 전체(과거 포함, 시각순) — 리포트 캘린더 마커용."""
    start = datetime.strptime(month, "%Y-%m")
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT event_time, name, category, severity FROM macro_event "
            "WHERE event_time >= %s AND event_time < %s ORDER BY event_time",
            (start, end),
        )
        return cursor.fetchall()


def upcoming(days: int = 30) -> list[dict]:
    """지금부터 days일 안의 이벤트(시각순) — 대시보드 '다가오는 거시 이벤트' 표시용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT event_time, name, category, severity FROM macro_event "
            "WHERE event_time >= NOW() AND event_time < DATE_ADD(NOW(), INTERVAL %s DAY) "
            "ORDER BY event_time",
            (days,),
        )
        return cursor.fetchall()
