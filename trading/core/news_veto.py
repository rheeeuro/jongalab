"""뉴스 베토 — jongalab 판정(news_veto_verdict, severe=1)을 읽어 monitor 가 개장 즉시 전량매도.

jongalab workers/news_guard.py(평일 07:00~09:25)가 보유 종목의 밤사이 뉴스를 OpenAI 로 판정해
적재하고, 여기는 읽기 전용 조회만 한다(macro_gate 와 같은 cross-DB 패턴 — 도메인 경계는
'jongalab 판단 → trading 집행' 단방향 유지).

[안전] 조회 실패·비활성 → 빈 dict(미개입) — 하드손절/스탑/settle 09:28 데드라인이 그대로
백스톱이므로 이 게이트가 감시 루프를 막는 일은 없다. 실패 시 캐시를 남기지 않아 다음
폴링(15s)에서 곧바로 재조회된다(자가 복구).
15초 폴링이 jongalab DB 를 매번 때리지 않도록 NEWS_VETO_CACHE_SEC TTL 캐시를 둔다 —
판정(news_guard)이 5분 주기라 60초 지연은 실효 손실이 없다.
"""
import logging
import time
from datetime import datetime

from core.db import get_jongalab_db
from core.config import NEWS_VETO_ENABLED, NEWS_VETO_CACHE_SEC

logger = logging.getLogger("NewsVeto")

_cache: tuple[float, dict[str, dict]] | None = None  # (fetched_at monotonic, verdicts)


def fetch_severe_verdicts(verdict_date: str) -> dict[str, dict]:
    """오늘 severe=1 판정 조회 — {stk_cd: {stk_nm, confidence, category, reason}}."""
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT stk_cd, stk_nm, confidence, category, reason FROM news_veto_verdict "
            "WHERE verdict_date = %s AND severe = 1",
            (verdict_date,),
        )
        return {r["stk_cd"]: r for r in cursor.fetchall()}


def get_severe_verdicts() -> dict[str, dict]:
    """monitor 폴링용 진입점 — TTL 캐시 + 실패 시 미개입(빈 dict)."""
    global _cache
    if not NEWS_VETO_ENABLED:
        return {}
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < NEWS_VETO_CACHE_SEC:
        return _cache[1]
    try:
        verdicts = fetch_severe_verdicts(datetime.now().strftime("%Y%m%d"))
    except Exception as e:
        logger.warning("news_veto_verdict 조회 실패 — 미개입(빈 목록, 다음 폴링 재조회): %s", e)
        return {}
    _cache = (now, verdicts)
    return verdicts
