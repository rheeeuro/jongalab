"""매수 시그널 큐 — jongalab(closing_bet)이 적재, trading 이 소비.

두 도메인을 잇는 유일한 결합점. shape 변경은 양쪽 합의 필요.
상태 흐름: pending → executing → done / rejected / expired
"""
from typing import Optional

from core.db import get_db


def get_name_map() -> dict:
    """종목코드 → 종목명 맵 (대시보드 표시용). 시그널에 등장한 모든 종목."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT stk_cd, MAX(stk_nm) AS nm FROM trade_signal "
            "WHERE stk_nm IS NOT NULL GROUP BY stk_cd"
        )
        return {r["stk_cd"]: r["nm"] for r in cursor.fetchall()}


def get_signals_by_date(trade_date: str) -> list[dict]:
    """해당 거래일 전체 시그널 (상태 무관, 대시보드용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM trade_signal WHERE trade_date = %s ORDER BY rank_no ASC",
            (trade_date,),
        )
        return cursor.fetchall()


def get_pending_signals(trade_date: str) -> list[dict]:
    """집행 대기(pending) 시그널 조회 (해당 거래일)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM trade_signal "
            "WHERE trade_date = %s AND status = 'pending' "
            "ORDER BY rank_no ASC",
            (trade_date,),
        )
        return cursor.fetchall()


def update_status(signal_id: int, status: str, note: Optional[str] = None) -> None:
    """시그널 상태 전이."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE trade_signal SET status = %s, note = %s WHERE id = %s",
            (status, note, signal_id),
        )
        conn.commit()


# TODO: insert_signal() — jongalab 측 어댑터에서 호출(또는 jongalab repository 에서 직접 INSERT)
