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


def has_fresh_signals(trade_date: str, since: str) -> bool:
    """since(YYYY-MM-DD HH:MM:SS) 이후 갱신된 시그널 존재 여부.

    closing_bet 은 30분마다 재실행하며 push 때 updated_at 을 항상 갱신한다.
    매수 워커가 윈도우 시작(15:00/19:30) 이후 갱신을 감지하면 그 회차 closing_bet 가
    종목 추천을 마쳤다는 신호로 쓴다(같은 분에 동시 기동되는 경쟁 방지).
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COUNT(*) AS n FROM trade_signal "
            "WHERE trade_date = %s AND updated_at >= %s",
            (trade_date, since),
        )
        return (cursor.fetchone() or {}).get("n", 0) > 0


def update_status(signal_id: int, status: str, note: Optional[str] = None) -> None:
    """시그널 상태 전이."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE trade_signal SET status = %s, note = %s WHERE id = %s",
            (status, note, signal_id),
        )
        conn.commit()


# TODO: insert_signal() — jongalab 측 어댑터에서 호출(또는 jongalab repository 에서 직접 INSERT)
