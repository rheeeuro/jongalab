"""매수 시그널 핸드오프 — closing_bet 후보를 trading DB(trade_signal)에 적재.

두 도메인(jongalab 분석 ↔ trading 집행)의 유일한 결합점. trading 이 소비한다.
closing_bet 은 9~18시 30분마다 재실행되므로 (trade_date, stk_cd) UNIQUE 로 멱등 처리:
재실행 시 점수·순위만 갱신하고 status 는 보존한다(이미 done/skipped 면 재집행하지 않음).
"""
import logging

from core.db import get_trading_db

logger = logging.getLogger("TradeSignal")


def push_trade_signals(trade_date: str, candidates: list[dict]) -> int:
    """후보 목록을 trade_signal 에 upsert. 반영된 행 수 반환.

    candidates: [{stk_cd, stk_nm, rank_no, score}, ...]
    신규는 status='pending' 으로 삽입, 기존은 stk_nm/rank_no/score 만 갱신(status 보존).
    """
    if not candidates:
        return 0

    rows = [
        (
            trade_date,
            c["stk_cd"],
            c.get("stk_nm"),
            c.get("rank_no"),
            c.get("score"),
        )
        for c in candidates
    ]
    with get_trading_db() as (conn, cursor):
        cursor.executemany(
            """INSERT INTO trade_signal (trade_date, stk_cd, stk_nm, rank_no, score, status)
               VALUES (%s, %s, %s, %s, %s, 'pending')
               ON DUPLICATE KEY UPDATE
                   stk_nm = VALUES(stk_nm),
                   rank_no = VALUES(rank_no),
                   score = VALUES(score)""",
            rows,
        )
        conn.commit()
        return cursor.rowcount
