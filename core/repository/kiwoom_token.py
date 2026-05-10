"""키움 액세스 토큰 데이터 접근 (단일행, id=1)"""
from typing import Optional

from core.db import get_db


def get_token() -> Optional[dict]:
    """저장된 토큰 조회. 없으면 None."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT access_token, expires_dt, issued_at, updated_at "
            "FROM kiwoom_token WHERE id = 1"
        )
        return cursor.fetchone()


def save_token(access_token: str, expires_dt: Optional[str]) -> None:
    """UPSERT id=1"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO kiwoom_token (id, access_token, expires_dt)
               VALUES (1, %s, %s)
               ON DUPLICATE KEY UPDATE access_token = %s, expires_dt = %s""",
            (access_token, expires_dt, access_token, expires_dt),
        )
        conn.commit()


def clear_token() -> None:
    """토큰 행 삭제 (revoke 후 정리용)"""
    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM kiwoom_token WHERE id = 1")
        conn.commit()
