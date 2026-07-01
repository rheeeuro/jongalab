"""뉴스 속보 언급 데이터 접근 (news_mention).

고빈도 뉴스 채널을 LLM 없이 종목 사전매칭만으로 적재한다. content_analysis 와 분리해
'재료 감지 신호'로만 쓰며, 오늘 언급 건수/헤드라인을 closing_bet Phase 2 가 조회한다.
"""
import json
from datetime import datetime

from core.db import get_db


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
