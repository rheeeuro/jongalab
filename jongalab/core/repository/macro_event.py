"""macro_event(거시 이벤트 캘린더) 접근 — 수동 시드 일정의 고갈 감시용 조회.

캘린더 자체는 sql/18. migrate_macro_event.sql 로 수동 시드하고,
trading macro_gate 가 매수 시점에 읽기 전용으로 조회한다(이 저장소는 jongalab 워커용).
"""
from datetime import datetime

from core.db import get_db


def last_event_time() -> datetime | None:
    """가장 늦은 이벤트 시각 — 캘린더가 언제까지 시드돼 있는지(고갈 임박 판정용)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT MAX(event_time) AS last_ev FROM macro_event")
        row = cursor.fetchone()
        return row["last_ev"] if row else None


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
