"""불변 감사로그 — 모든 주문 의도 + 키움 응답 원문을 append-only 로 적재.

자동매매의 사후 추적·정산 근거. UPDATE/DELETE 하지 않는다.
"""
import json
from typing import Optional

from core.db import get_db


def append(event: str, stk_cd: Optional[str], payload: dict) -> None:
    """감사 이벤트 1건 기록 (payload 는 JSON 직렬화)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO audit_log (event, stk_cd, payload) VALUES (%s, %s, %s)",
            (event, stk_cd, json.dumps(payload, ensure_ascii=False, default=str)),
        )
        conn.commit()
