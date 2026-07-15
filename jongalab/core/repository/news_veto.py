"""뉴스 베토 판정 데이터 접근 (news_veto_verdict).

workers/news_guard.py 가 보유 종목의 밤사이 중대 악재 판정을 (verdict_date, stk_cd) 단위로
upsert 하고, trading workers/monitor.py 가 severe=1 을 읽기 전용 조회해 개장 즉시 전량 매도한다.

강등 금지 규칙: 한 번 severe=1 이 된 행은 이후 재판정이 severe=0 이어도 뒤집지 않는다
(GREATEST upsert). 매도가 진행 중인데 판정이 흔들려 감시가 풀리는 레이스를 막는다 —
호출부(news_guard)도 severe 확정 행은 재판정 자체를 건너뛰므로 실제로는 방어선 역할만 한다.
"""
import json
from datetime import datetime

from core.db import get_db


def get_verdict(verdict_date: str, stk_cd: str) -> dict | None:
    """해당 거래일·종목의 판정 1행 (없으면 None). news_max_at 은 datetime 그대로 반환."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT verdict_date, stk_cd, stk_nm, severe, confidence, category,
                   reason, news_max_at, updated_at
            FROM news_veto_verdict
            WHERE verdict_date = %s AND stk_cd = %s
            """,
            (verdict_date, stk_cd),
        )
        return cursor.fetchone()


def upsert_verdict(verdict_date: str, stk_cd: str, stk_nm: str | None, severe: int,
                   confidence: int, category: str, reason: str,
                   headlines: list[str], news_max_at: datetime, model: str) -> None:
    """판정 upsert. severe 는 GREATEST 로 1→0 강등 금지, 나머지 필드는
    '비-severe 재판정이 severe 행을 덮어쓰지 않는' 조건(IF VALUES(severe) >= severe)으로만 갱신.
    (MySQL 의 ON DUPLICATE KEY UPDATE 는 좌→우 평가라 severe 갱신을 마지막에 둔다.)
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO news_veto_verdict
                (verdict_date, stk_cd, stk_nm, severe, confidence, category,
                 reason, headlines, news_max_at, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                stk_nm      = IF(VALUES(severe) >= severe, VALUES(stk_nm), stk_nm),
                confidence  = IF(VALUES(severe) >= severe, VALUES(confidence), confidence),
                category    = IF(VALUES(severe) >= severe, VALUES(category), category),
                reason      = IF(VALUES(severe) >= severe, VALUES(reason), reason),
                headlines   = IF(VALUES(severe) >= severe, VALUES(headlines), headlines),
                news_max_at = IF(VALUES(severe) >= severe, VALUES(news_max_at), news_max_at),
                model       = IF(VALUES(severe) >= severe, VALUES(model), model),
                severe      = GREATEST(severe, VALUES(severe))
            """,
            (verdict_date, stk_cd, stk_nm, int(severe), int(confidence), category,
             (reason or "")[:500], json.dumps(headlines, ensure_ascii=False),
             news_max_at, model),
        )
        conn.commit()


def list_severe(verdict_date: str) -> list[dict]:
    """해당 거래일의 severe=1 판정 목록 (점검·표시용 — trading 쪽은 자체 조회를 쓴다)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT stk_cd, stk_nm, confidence, category, reason, news_max_at, updated_at
            FROM news_veto_verdict
            WHERE verdict_date = %s AND severe = 1
            ORDER BY updated_at DESC
            """,
            (verdict_date,),
        )
        return cursor.fetchall()
