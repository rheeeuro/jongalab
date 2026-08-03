"""코스피200 야간선물 1분봉 데이터 접근 (append-only 시계열, sql/46 참고).

WebSocket 워커(workers/kis_night_futures_ws.py)가 save_bar, market_data 가 get_bars 를 쓴다.
현재가 표시는 단일행 kis_night_future 가 계속 담당한다 — 이 테이블은 **이력 전용**이다
(futures_gate 모멘텀 축 백테스트 + 야간선물 상세 차트).
"""
from datetime import datetime
from typing import Optional

from core.db import get_db


def save_bar(
    symbol: str,
    bar_time: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    change_percent: Optional[float],
    prev_close: Optional[float],
    tick_count: int,
) -> None:
    """1분봉 1행 append (symbol+bar_time 중복이면 병합).

    재접속으로 같은 분이 두 번 기록될 수 있어 병합 규칙을 둔다: 시가는 처음 것을 유지하고
    고가/저가는 확장, 종가·등락률은 나중 값으로 갱신, 체결 수는 누적한다. 이렇게 해야
    끊김 구간이 '봉 하나가 통째로 덮어써진' 형태로 왜곡되지 않는다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO kis_night_future_bar
                   (symbol, bar_time, `open`, `high`, `low`, `close`,
                    change_percent, prev_close, tick_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   `high`         = GREATEST(`high`, VALUES(`high`)),
                   `low`          = LEAST(`low`, VALUES(`low`)),
                   `close`        = VALUES(`close`),
                   change_percent = VALUES(change_percent),
                   prev_close     = VALUES(prev_close),
                   tick_count     = tick_count + VALUES(tick_count)""",
            (symbol, bar_time, open_, high, low, close,
             change_percent, prev_close, tick_count),
        )
        conn.commit()


def get_bars(start: datetime, end: Optional[datetime] = None,
             limit: int = 2000) -> list[dict]:
    """[start, end) 구간의 1분봉을 시간 오름차순으로. end 생략 시 start 이후 전부.

    limit 은 폭주 방어용 상한이며, 넘칠 경우 **최신 쪽**을 남긴다(차트는 최근이 중요).
    """
    sql = ("SELECT symbol, bar_time, `open`, `high`, `low`, `close`, "
           "change_percent, prev_close, tick_count "
           "FROM kis_night_future_bar WHERE bar_time >= %s")
    params: list = [start]
    if end is not None:
        sql += " AND bar_time < %s"
        params.append(end)
    sql += " ORDER BY bar_time DESC LIMIT %s"
    params.append(limit)

    with get_db() as (conn, cursor):
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
    return list(reversed(rows))
