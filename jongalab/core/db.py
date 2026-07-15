"""
DB 연결 관리 모듈 - context manager로 연결 누수 방지
"""
from contextlib import contextmanager
import mysql.connector
from core.config import DB_CONFIG, TRADING_DB_CONFIG


def get_connection():
    """단순 DB 연결 반환 (수동 close 필요)"""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def get_db():
    """
    Context manager로 안전한 DB 연결 관리.
    with 블록을 벗어나면 자동으로 커서와 연결을 닫아줍니다.
    
    사용법:
        with get_db() as (conn, cursor):
            cursor.execute("SELECT ...")
            result = cursor.fetchall()
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()


@contextmanager
def get_trading_db():
    """trading DB 안전 연결. closing_bet 핸드오프(trade_signal 쓰기) +
    news_guard 보유 포지션 조회(position 읽기 전용)에만 쓴다."""
    conn = mysql.connector.connect(**TRADING_DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()
