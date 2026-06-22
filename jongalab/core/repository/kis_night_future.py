"""코스피200 야간선물 실시간 시세 데이터 접근 (단일행, id=1).

WebSocket 워커(workers/kis_night_futures_ws.py)가 save_*, market_data 가 get_* 를 쓴다.
신선도 판단은 DB 시계 기준(TIMESTAMPDIFF)으로 계산해 파이썬/DB 타임존 차이를 피한다.
"""
from typing import Optional

from core.db import get_db


def save_night_future(
    symbol: str,
    price: float,
    change_val: Optional[float],
    change_percent: Optional[float],
    quote_time: Optional[str],
) -> None:
    """UPSERT id=1 (체결 틱마다 갱신)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO kis_night_future
                   (id, symbol, price, change_val, change_percent, quote_time)
               VALUES (1, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   symbol = %s, price = %s, change_val = %s,
                   change_percent = %s, quote_time = %s""",
            (symbol, price, change_val, change_percent, quote_time,
             symbol, price, change_val, change_percent, quote_time),
        )
        conn.commit()


def get_night_future() -> Optional[dict]:
    """야간선물 행 조회. age_sec = 마지막 갱신 후 경과초(DB 시계 기준)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT symbol, price, change_val, change_percent, quote_time, "
            "TIMESTAMPDIFF(SECOND, updated_at, NOW()) AS age_sec "
            "FROM kis_night_future WHERE id = 1"
        )
        return cursor.fetchone()
