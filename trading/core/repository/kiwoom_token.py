"""키움 액세스 토큰 조회 (읽기 전용).

토큰의 발급/갱신/폐기는 kiwoom 서버 워커(kiwoom_token_refresh)가 전담한다.
trading 은 공유 kiwoom DB 에서 토큰을 **읽기만** 한다 — 절대 쓰지 않는다.
"""
from typing import Optional

from core.db import get_kiwoom_db


def get_token() -> Optional[dict]:
    """저장된 키움 토큰 조회 (kiwoom DB). 없으면 None."""
    with get_kiwoom_db() as (conn, cursor):
        cursor.execute(
            "SELECT access_token, expires_dt, issued_at, updated_at "
            "FROM kiwoom_token WHERE id = 1"
        )
        return cursor.fetchone()
