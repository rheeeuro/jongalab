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


def list_recent(limit: int = 50) -> list[dict]:
    """최근 감사 이벤트 (대시보드용, 최신순). payload 는 dict 로 파싱."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, event, stk_cd, payload, created_at "
            "FROM audit_log ORDER BY id DESC LIMIT %s",
            (int(limit),),
        )
        rows = cursor.fetchall()
    for r in rows:
        if isinstance(r.get("payload"), str):
            try:
                r["payload"] = json.loads(r["payload"])
            except (ValueError, TypeError):
                pass
    return rows
