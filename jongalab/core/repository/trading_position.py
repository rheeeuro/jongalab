"""trading DB 포지션 읽기 전용 조회 (news_guard 전용).

position 테이블은 trading 도메인(주문 집행)의 소스 오브 트루스다. jongalab 쪽에서는
'지금 보유 중인 종목' 집합이 필요한 workers/news_guard.py 만 읽는다 — **쓰기 금지**
(포지션 변경은 trading 의 체결 동기화·리컨사일만 한다).
"""
from core.db import get_trading_db


def get_open_positions() -> list[dict]:
    """보유 중(qty > 0)인 포지션 목록: [{stk_cd, qty, avg_price}]."""
    with get_trading_db() as (conn, cursor):
        cursor.execute("SELECT stk_cd, qty, avg_price FROM position WHERE qty > 0")
        return cursor.fetchall()
