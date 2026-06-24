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


def raise_stop(trade_date: str, stk_cd: str, new_stop: int, note: str = "") -> bool:
    """트레일링 스탑 — 새 스탑선이 기존보다 높을 때만 끌어올린다(단조 증가, 절대 내리지 않음).

    고점 추종 트레일링은 stop = max(기존 stop, 현재가*(1-TRAIL_PCT/100)) 로 충분하다:
    상수배의 시간축 max == (max 현재가=고점)의 상수배 이므로 별도 peak 컬럼이 필요 없다.
    active=1 인 계획만, 그리고 실제로 더 높을 때만 갱신해 멱등·하향불가를 보장한다.
    실제로 끌어올렸으면 True.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """UPDATE settle_plan SET stop_price=%s, note=%s
               WHERE trade_date=%s AND stk_cd=%s AND active=1 AND %s > stop_price""",
            (new_stop, note, trade_date, stk_cd, new_stop),
        )
        conn.commit()
        return cursor.rowcount > 0


def deactivate(trade_date: str, stk_cd: str, note: str = "") -> None:
    """청산 완료/중단 — 감시 해제."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE settle_plan SET active=0, note=%s WHERE trade_date=%s AND stk_cd=%s",
            (note, trade_date, stk_cd),
        )
        conn.commit()
