"""뉴스 속보 언급 데이터 접근 (news_mention).

고빈도 뉴스 채널을 LLM 없이 종목 사전매칭만으로 적재한다. content_analysis 와 분리해
'재료 감지 신호'로만 쓰며, 오늘 언급 건수/헤드라인을 closing_bet Phase 2 가 조회한다.
"""
import json
import re
from datetime import datetime

from core.db import get_db

# 헤드라인 dedup 정규화: 발행처 대괄호 제거 후 한글/영숫자만 남긴다.
# 같은 기사가 여러 채널에 복제될 때 채널별 말머리·구두점 차이를 흡수한다.
_BRACKET_RE = re.compile(r"\[[^\]]*\]|【[^】]*】")
_NON_WORD_RE = re.compile(r"[^가-힣A-Za-z0-9]+")


def _normalize_headline(headline: str) -> str:
    """dedup 키용 정규화. 빈 문자열이면 dedup 불가 → 호출부에서 원문 유지."""
    text = _BRACKET_RE.sub(" ", headline or "")
    return _NON_WORD_RE.sub("", text).lower()


def save_news_mentions(rows: list[dict]) -> int:
    """뉴스 언급을 일괄 저장 (중복 URL·종목 조합은 무시).

    rows 항목: {ticker, company_name, headline, source_url, channel_name, published_at}
    반환: 실제 삽입된 행 수.
    """
    if not rows:
        return 0
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT IGNORE INTO news_mention
                (ticker, company_name, headline, source_url, channel_name, published_at)
            VALUES (%(ticker)s, %(company_name)s, %(headline)s, %(source_url)s,
                    %(channel_name)s, %(published_at)s)
            """,
            rows,
        )
        inserted = cursor.rowcount
        conn.commit()
    return inserted


def get_today_news_count_by_stock(stock_code: str) -> int:
    """오늘 수집된 특정 종목의 뉴스 언급 건수 (created_at = 오늘)."""
    code = stock_code.split(".")[0].split("_")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE()
            """,
            (code,),
        )
        return int(cursor.fetchone()["cnt"])


def get_today_news_stats_by_stock(stock_code: str) -> dict:
    """오늘 뉴스 언급의 연구 라벨 집계 (closing_bet 이 daily_stock_report 에 저장).

    반환: {count, unique_count, pm_count, first_today, prior_avg}
      - count        : 오늘 총 언급 건수 (기존 get_today_news_count_by_stock 과 동일 기준)
      - unique_count : 헤드라인 정규화 dedup 고유 기사 수 (채널 복제 제거)
      - pm_count     : 12시 이후 언급 수 (종가베팅 신선도 — 장중 늦게 터진 재료)
      - first_today  : 직전 14일(보존 주기) 내 언급 이력이 없으면 1
      - prior_avg    : 직전 7일 일평균 언급 수 (서프라이즈 배수의 분모). 오늘 언급 없으면 None
    """
    code = stock_code.split(".")[0].split("_")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT headline, created_at FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE()
            """,
            (code,),
        )
        today_rows = cursor.fetchall()
        if not today_rows:
            return {"count": 0, "unique_count": 0, "pm_count": 0,
                    "first_today": 0, "prior_avg": None}

        cursor.execute(
            """
            SELECT COUNT(*) AS prior_total,
                   SUM(created_at >= CURDATE() - INTERVAL 7 DAY) AS prior_7d
            FROM news_mention
            WHERE ticker = %s AND created_at < CURDATE()
            """,
            (code,),
        )
        prior = cursor.fetchone()

    unique_keys = {_normalize_headline(r["headline"]) or (r["headline"] or "")
                   for r in today_rows}
    pm_count = sum(
        1 for r in today_rows
        if isinstance(r.get("created_at"), datetime) and r["created_at"].hour >= 12
    )
    prior_total = int(prior["prior_total"] or 0)
    prior_7d = int(prior["prior_7d"] or 0)
    return {
        "count": len(today_rows),
        "unique_count": len(unique_keys),
        "pm_count": pm_count,
        "first_today": 1 if prior_total == 0 else 0,
        "prior_avg": round(prior_7d / 7.0, 2),
    }


def get_today_news_by_stock(stock_code: str, limit: int = 15) -> list[dict]:
    """오늘 수집된 특정 종목의 뉴스 헤드라인 목록 (최신순, 표시·요약용)."""
    code = stock_code.split(".")[0].split("_")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT headline, source_url, channel_name, created_at
            FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE()
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (code, int(limit)),
        )
        results = cursor.fetchall()
        for row in results:
            if isinstance(row.get("created_at"), datetime):
                row["created_at"] = row["created_at"].isoformat()
        return results


def get_news_since(stock_code: str, since_dt: datetime, limit: int = 30) -> list[dict]:
    """특정 종목의 since_dt 이후 뉴스 언급 (시간순 ASC — 뉴스 베토 판정용).

    get_today_news_by_stock 은 CURDATE() 기준이라 전일 저녁(매수 후 밤사이) 뉴스를 놓친다 —
    오버나잇 창(전거래일 15:00~) 조회는 이 함수를 쓴다. created_at 은 datetime 그대로 반환한다
    (호출부 news_guard 가 news_max_at 비교에 사용).
    """
    code = stock_code.split(".")[0].split("_")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT headline, company_name, channel_name, created_at
            FROM news_mention
            WHERE ticker = %s AND created_at >= %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (code, since_dt, int(limit)),
        )
        return cursor.fetchall()


def get_news_heat(hours: int = 24, limit: int = 20) -> list[dict]:
    """최근 N시간 뉴스 언급이 많은 종목 순위 (프론트 '뉴스 재료' 카드용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT ticker,
                   MAX(company_name) AS company_name,
                   COUNT(*) AS mention_count,
                   MAX(created_at) AS last_at
            FROM news_mention
            WHERE created_at >= NOW() - INTERVAL %s HOUR
            GROUP BY ticker
            ORDER BY mention_count DESC, last_at DESC
            LIMIT %s
            """,
            (int(hours), int(limit)),
        )
        results = cursor.fetchall()
        for row in results:
            if isinstance(row.get("last_at"), datetime):
                row["last_at"] = row["last_at"].isoformat()
        return results


def delete_old_news_mentions(days: int = 14) -> int:
    """N일 이전 뉴스 언급 삭제 (cleanup_content 워커가 호출). 삭제 행 수 반환."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM news_mention WHERE created_at < NOW() - INTERVAL %s DAY",
            (int(days),),
        )
        deleted = cursor.rowcount
        conn.commit()
    return deleted
