"""
DB 연결 관리 모듈 - context manager로 연결 누수 방지.

get_db()        — 트레이딩 전용 DB (읽기/쓰기)
get_kiwoom_db() — 키움 토큰 공유 DB (읽기 전용 — 토큰 조회용)
"""
from contextlib import contextmanager
import mysql.connector
from core.config import DB_CONFIG, KIWOOM_DB_CONFIG, JONGALAB_DB_CONFIG


def get_connection():
    """단순 DB 연결 반환 (수동 close 필요)"""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def get_db():
    """
    트레이딩 DB 안전 연결 (context manager).

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
def get_kiwoom_db():
    """키움 토큰 공유 DB 안전 연결 (토큰 읽기 전용)."""
    conn = mysql.connector.connect(**KIWOOM_DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()


@contextmanager
def get_jongalab_db():
    """jongalab DB 안전 연결 (텔레그램 관리자 chat id 읽기 전용)."""
    conn = mysql.connector.connect(**JONGALAB_DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()
