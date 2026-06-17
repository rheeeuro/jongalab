"""청산 계획 데이터 접근 — 시초가 2단계 매도의 단계 간 상태.

NXT 08:05 단계가 갭 방향·시초가·스탑선을 기록하고, 1분 모니터와 KRX 09:05 단계가 읽는다.
active=0 이 되면 해당 종목 청산이 완료(또는 중단)된 것.
"""
from typing import Optional

from core.db import get_db


def upsert_plan(trade_date: str, stk_cd: str, gap_dir: str, avg_price: int,
                nxt_open: int, stop_price: int, note: str = "") -> None:
    """NXT 단계에서 청산 계획 기록(멱등)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO settle_plan
               (trade_date, stk_cd, gap_dir, avg_price, nxt_open, stop_price, active, note)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s)
               ON DUPLICATE KEY UPDATE
                   gap_dir=VALUES(gap_dir), avg_price=VALUES(avg_price),
                   nxt_open=VALUES(nxt_open), stop_price=VALUES(stop_price),
                   active=1, note=VALUES(note)""",
            (trade_date, stk_cd, gap_dir, avg_price, nxt_open, stop_price, note),
        )
        conn.commit()


def get_plan(trade_date: str, stk_cd: str) -> Optional[dict]:
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM settle_plan WHERE trade_date=%s AND stk_cd=%s",
            (trade_date, stk_cd),
        )
        return cursor.fetchone()


def get_by_date(trade_date: str) -> list[dict]:
    """해당 거래일 청산계획 전체 — 일별 상세(갭상승 여부)용."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM settle_plan WHERE trade_date=%s", (trade_date,))
        return cursor.fetchall()


def get_active_plans() -> list[dict]:
    """현재 감시 대상(active=1) 청산 계획 — 1분 모니터·KRX 단계가 사용."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM settle_plan WHERE active = 1")
        return cursor.fetchall()


def deactivate(trade_date: str, stk_cd: str, note: str = "") -> None:
    """청산 완료/중단 — 감시 해제."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE settle_plan SET active=0, note=%s WHERE trade_date=%s AND stk_cd=%s",
            (note, trade_date, stk_cd),
        )
        conn.commit()
