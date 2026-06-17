"""매수 제외 종목(blocklist) 데이터 접근.

signal_executor 가 매수 직전 get_codes() 로 검사한다.
대시보드(PUT /blocklist)에서 전체 목록을 교체한다.
"""
from core.db import get_db


def get_codes() -> set[str]:
    """제외 종목코드 집합 (매수 차단 검사용)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT stk_cd FROM blocklist")
        return {r["stk_cd"] for r in cursor.fetchall()}


def get_all() -> list[dict]:
    """제외 목록 전체 (대시보드용, 최신순)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT stk_cd, reason, created_at FROM blocklist ORDER BY created_at DESC")
        return cursor.fetchall()


def replace_all(items: list[dict]) -> list[dict]:
    """제외 목록 전체 교체. items: [{stk_cd, reason?}, ...]"""
    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM blocklist")
        for it in items:
            code = (it.get("stk_cd") or "").strip()
            if not code:
                continue
            cursor.execute(
                "INSERT INTO blocklist (stk_cd, reason) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE reason = VALUES(reason)",
                (code, it.get("reason")),
            )
        conn.commit()
    return get_all()
