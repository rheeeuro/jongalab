"""콘텐츠 분석 데이터 접근"""
import json
import math
import logging
from datetime import datetime

from core.db import get_db
from core.ai_utils import remove_markdown_code_blocks


def _parse_json_columns(row: dict) -> None:
    """content_analysis 행의 JSON 문자열 컬럼(tags/stock_calls)을 파이썬 객체로 파싱(in-place).
    누락/파싱 실패 시 tags=[], stock_calls=[] 로 채운다. tldr 은 문자열 그대로 둔다.
    """
    for col in ("tags", "stock_calls"):
        raw = row.get(col)
        if isinstance(raw, str) and raw:
            try:
                row[col] = json.loads(raw)
            except Exception:
                row[col] = []
        elif raw is None:
            row[col] = []
    if "tldr" in row and row["tldr"] is None:
        row["tldr"] = ""


def get_contents_paginated(page: int = 1, limit: int = 12) -> dict:
    """페이지네이션된 콘텐츠 목록 조회"""
    with get_db() as (conn, cursor):
        offset = (page - 1) * limit

        where_clause = "WHERE created_at >= NOW() - INTERVAL 7 DAY"

        cursor.execute(
            f"SELECT COUNT(*) as total_count FROM content_analysis {where_clause}",
        )
        total_count = cursor.fetchone()["total_count"]

        cursor.execute(
            f"""
            SELECT id, external_id, source_name, title,
                   analysis_content, sentiment_score,
                   platform, source_url, created_at, related_tickers,
                   tldr, tags, stock_calls
            FROM content_analysis {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        result = cursor.fetchall()

        for row in result:
            if row["created_at"]:
                row["created_at"] = str(row["created_at"])
            if row["sentiment_score"] is None:
                row["sentiment_score"] = 50
            if row.get("related_tickers"):
                try:
                    row["related_tickers"] = json.loads(row["related_tickers"])
                except Exception:
                    row["related_tickers"] = []
            else:
                row["related_tickers"] = []
            _parse_json_columns(row)

        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1

        return {
            "data": result,
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next_page": page < total_pages,
                "has_prev_page": page > 1,
            },
        }


def get_contents_by_ticker(ticker: str) -> list[dict]:
    """특정 티커 관련 콘텐츠 조회"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT * FROM content_analysis
            WHERE created_at >= NOW() - INTERVAL 7 DAY
              AND related_tickers LIKE %s
            ORDER BY created_at DESC
            """,
            (f"%{ticker}%",),
        )
        results = cursor.fetchall()
        for row in results:
            if isinstance(row["created_at"], datetime):
                row["created_at"] = row["created_at"].isoformat()
            _parse_json_columns(row)
        return results


def is_content_processed(external_id: str) -> bool:
    """이미 처리된 콘텐츠인지 확인"""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT count(*) as cnt FROM content_analysis WHERE external_id = %s",
            (external_id,),
        )
        return cursor.fetchone()["cnt"] > 0


def save_content_analysis(
    external_id: str,
    source_name: str,
    title: str,
    content: str,
    score: int,
    source_url: str,
    related_tickers: list,
    platform: str,
    tldr: str = "",
    tags: list | None = None,
    stocks: list | None = None,
):
    """콘텐츠 분석 결과 저장 (telegram / youtube 공통).
    related_tickers의 종목별 섹터를 동기 조회해 ticker_sectors에 함께 저장.
    조회 실패는 sector=None으로 채워 콘텐츠 저장 자체는 막지 않음.

    구조화 요약 필드도 함께 저장:
    - tldr: 한 줄 대표 요약
    - tags: 테마 해시태그 리스트 → tags(JSON)
    - stocks: [{name,stance,conviction,horizon,reason}] → name을 ticker로 보강해 stock_calls(JSON)
    """
    content = remove_markdown_code_blocks(content)
    tags = tags or []
    stocks = stocks or []

    ticker_sectors_json: str | None = None
    try:
        from core.sector_resolver import resolve_sectors  # 지연 import: 순환참조 방지
        sectors = resolve_sectors(related_tickers or [])
        if sectors:
            ticker_sectors_json = json.dumps(sectors, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"섹터 enrich 실패 (계속 진행): {e}")

    # stocks 의 name 을 related_tickers 로 매칭해 ticker 를 붙인다 (프론트 종목 링크용).
    name_to_ticker = {
        (t.get("name") or "").strip(): t.get("ticker")
        for t in (related_tickers or [])
    }
    stock_calls: list[dict] = []
    for s in stocks:
        nm = (s.get("name") or "").strip()
        if not nm:
            continue
        stock_calls.append({
            "name": nm,
            "ticker": name_to_ticker.get(nm),
            "stance": s.get("stance") or "중립",
            "conviction": s.get("conviction") or "",
            "horizon": s.get("horizon") or "",
            "reason": (s.get("reason") or "").strip(),
        })
    tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
    stock_calls_json = json.dumps(stock_calls, ensure_ascii=False) if stock_calls else None

    with get_db() as (conn, cursor):
        query = """
            INSERT INTO content_analysis
            (external_id, source_name, title, analysis_content, sentiment_score,
             source_url, related_tickers, platform, ticker_sectors,
             tldr, tags, stock_calls)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            external_id, source_name, title, content, score,
            source_url, json.dumps(related_tickers), platform,
            ticker_sectors_json,
            tldr or None, tags_json, stock_calls_json,
        ))
        conn.commit()
    logging.info(f"DB 저장 완료: {title} (점수: {score}, 티커: {related_tickers})")


def delete_old_content_analysis(months: int = 3) -> int:
    """N개월 이전에 수집된 콘텐츠 분석 데이터를 삭제한다.

    조회는 모두 최근 데이터(7일/24시간/오늘)만 보므로, 오래된 행은 보관 가치가 없다.
    매일 cron(cleanup_content 워커)으로 실행해 테이블 비대화를 막는다.
    삭제된 행 수를 반환한다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM content_analysis WHERE created_at < NOW() - INTERVAL %s MONTH",
            (months,),
        )
        deleted = cursor.rowcount
        conn.commit()
    return deleted


def get_today_content_by_stock(stock_code: str) -> list[dict]:
    """오늘 날짜의 특정 종목 관련 콘텐츠 분석 조회 (ticker로 매칭)"""
    code_part = stock_code.split(".")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT id, title, analysis_content, sentiment_score,
                   source_name, platform, source_url, created_at
            FROM content_analysis
            WHERE DATE(created_at) = CURDATE()
              AND related_tickers LIKE %s
            ORDER BY created_at DESC
            """,
            (f"%{code_part}%",),
        )
        results = cursor.fetchall()
        for row in results:
            if isinstance(row["created_at"], datetime):
                row["created_at"] = row["created_at"].isoformat()
            if row["sentiment_score"] is None:
                row["sentiment_score"] = 50
        return results


def get_content_by_stock_and_date(
    stock_code: str, report_date: str
) -> list[dict]:
    """특정 날짜의 특정 종목 관련 콘텐츠 분석 조회 (ticker로 매칭)"""
    code_part = stock_code.split(".")[0]
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT id, title, analysis_content, sentiment_score,
                   source_name, platform, source_url, created_at
            FROM content_analysis
            WHERE DATE(created_at) = %s
              AND related_tickers LIKE %s
            ORDER BY created_at DESC
            """,
            (report_date, f"%{code_part}%"),
        )
        results = cursor.fetchall()
        for row in results:
            if isinstance(row["created_at"], datetime):
                row["created_at"] = row["created_at"].isoformat()
            if row["sentiment_score"] is None:
                row["sentiment_score"] = 50
        return results


def get_recent_analyses(hours: int = 24) -> list[dict]:
    """최근 N시간 내 수집된 분석 데이터 조회 (일일 요약용)"""
    with get_db() as (conn, cursor):
        query = """
            SELECT source_name, title, analysis_content, sentiment_score, related_tickers
            FROM content_analysis
            WHERE created_at >= NOW() - INTERVAL %s HOUR
        """
        cursor.execute(query, (hours,))
        return cursor.fetchall()


def get_mention_stats(hours: int = 12) -> dict:
    """최근 N시간 콘텐츠의 섹터/티커 언급 통계 (트리맵용).
    sector=None인 ticker는 통계에서 제외 (이전 합의).
    한 콘텐츠 내 동일 ticker는 1회만 카운트.
    """
    where = "WHERE created_at >= NOW() - INTERVAL %s HOUR"
    params: list = [hours]

    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM content_analysis {where}",
            tuple(params),
        )
        total_contents = cursor.fetchone()["cnt"]

        cursor.execute(
            f"""
            SELECT id, related_tickers, ticker_sectors, sentiment_score
            FROM content_analysis
            {where}
              AND related_tickers IS NOT NULL
              AND ticker_sectors IS NOT NULL
            """,
            tuple(params),
        )
        rows = cursor.fetchall()

    # 집계: (sector, ticker) -> {mention_count, sentiments[], name}
    sector_ticker: dict[tuple[str, str], dict] = {}
    name_lookup: dict[str, str] = {}
    total_mentions = 0
    dropped = 0

    for row in rows:
        try:
            tickers = json.loads(row["related_tickers"]) if isinstance(row["related_tickers"], str) else (row["related_tickers"] or [])
            sector_map_list = json.loads(row["ticker_sectors"]) if isinstance(row["ticker_sectors"], str) else (row["ticker_sectors"] or [])
        except Exception:
            continue

        # ticker -> name 룩업
        for t in tickers:
            tk = (t.get("ticker") or "").strip()
            if tk and tk not in name_lookup:
                name_lookup[tk] = (t.get("name") or "").strip()

        # ticker -> sector 매핑
        sector_by_ticker = {
            (s.get("ticker") or "").strip(): (s.get("sector") or None)
            for s in sector_map_list
        }

        seen_in_content: set[str] = set()
        for tk, sector in sector_by_ticker.items():
            if not tk or tk in seen_in_content:
                continue
            seen_in_content.add(tk)
            if not sector:
                dropped += 1
                continue
            key = (sector, tk)
            entry = sector_ticker.setdefault(key, {"count": 0, "sent_sum": 0, "sent_n": 0})
            entry["count"] += 1
            score = row.get("sentiment_score")
            if score is not None:
                entry["sent_sum"] += int(score)
                entry["sent_n"] += 1
            total_mentions += 1

    # 섹터 단위로 묶기
    sectors_agg: dict[str, dict] = {}
    for (sector, ticker), e in sector_ticker.items():
        sec = sectors_agg.setdefault(sector, {"sector": sector, "mention_count": 0, "tickers": []})
        sec["mention_count"] += e["count"]
        avg_sent = round(e["sent_sum"] / e["sent_n"]) if e["sent_n"] > 0 else None
        sec["tickers"].append({
            "ticker": ticker,
            "name": name_lookup.get(ticker, ""),
            "mention_count": e["count"],
            "avg_sentiment": avg_sent,
        })

    sectors_list = sorted(sectors_agg.values(), key=lambda s: s["mention_count"], reverse=True)
    for sec in sectors_list:
        sec["tickers"].sort(key=lambda x: (-x["mention_count"], x["name"]))

    return {
        "window_hours": hours,
        "total_contents": total_contents,
        "total_mentions": total_mentions,
        "dropped_unmapped_count": dropped,
        "sectors": sectors_list,
    }
