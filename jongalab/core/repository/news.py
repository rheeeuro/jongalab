"""뉴스 속보 언급 데이터 접근 (news_mention).

두 소스가 같은 테이블에 들어온다 — 텔레그램 뉴스 채널(사명 사전매칭)과 네이버 증권
종목별 뉴스(종목코드 조회, 매칭 없음). content_analysis 와 분리해 '재료 감지 신호'로만
쓰며, 오늘 언급 건수/헤드라인을 closing_bet Phase 2 가 조회한다.

⚠️ **조회 함수는 전부 `_source_filter()` 를 통과한다.** 소스를 늘리면 news_count·
news_prior_avg·surprise 배수가 도입일에 계단식으로 튀고(실측 네이버 562행 vs 텔레그램
273행, 헤드라인 중복 2%뿐이라 상쇄 없이 순증), news_unique_count 를 쓰는 rule 3종 중
`veto_bad_news` 는 live = 자금 경로다. 그래서 적재는 무조건 하고 **소비만**
config.NEWS_ACTIVE_SOURCES(기본 telegram)로 막아 관측 기간을 둔다. 승격은 .env 한 줄.
새 조회 함수를 추가할 때도 이 필터를 빠뜨리지 말 것 — 빠뜨리면 게이트가 조용히 뚫린다.
"""
import json
import re
from datetime import datetime

from core.config import NEWS_ACTIVE_SOURCES
from core.db import get_db

# 헤드라인 dedup 정규화: 발행처 대괄호 제거 후 한글/영숫자만 남긴다.
# 같은 기사가 여러 채널에 복제될 때 채널별 말머리·구두점 차이를 흡수한다.
_BRACKET_RE = re.compile(r"\[[^\]]*\]|【[^】]*】")
_NON_WORD_RE = re.compile(r"[^가-힣A-Za-z0-9]+")


def _normalize_headline(headline: str) -> str:
    """dedup 키용 정규화. 빈 문자열이면 dedup 불가 → 호출부에서 원문 유지."""
    text = _BRACKET_RE.sub(" ", headline or "")
    return _NON_WORD_RE.sub("", text).lower()


# news_first_today 의 '첫 등장' 판정 창(일). **보존 기간과 분리해 명시한다** —
# 예전엔 하한이 없어서 사실상 cleanup_content 의 보존일(14)이 창이었다. 2026-07-31 에 네이버
# 병행 검증을 위해 보존을 30일로 늘리면서, 그대로 두면 라벨 뜻이 "14일 내 첫 등장"에서
# "30일 내"로 조용히 바뀌어 candidate rule `f1_fresh_news_unpriced` 의 입력이 흔들렸다.
# 값은 종전과 같은 14 이므로 지금 라벨값은 변하지 않는다(보존 14일 하에선 결과 동일).
_FIRST_TODAY_LOOKBACK_DAYS = 14


def _source_filter() -> tuple[str, tuple]:
    """소비 대상 소스 필터 — (SQL 조각, 바인딩 파라미터).

    조각은 항상 앞에 AND 가 붙는 형태로 돌려주므로 WHERE 절 뒤에 그대로 이어 붙인다.
    """
    placeholders = ", ".join(["%s"] * len(NEWS_ACTIVE_SOURCES))
    return f" AND source IN ({placeholders})", tuple(NEWS_ACTIVE_SOURCES)


def save_news_mentions(rows: list[dict]) -> int:
    """뉴스 언급을 일괄 저장 (중복 URL·종목 조합은 무시).

    rows 항목: {ticker, company_name, headline, source_url, channel_name, published_at}
      + 선택 {source, created_at}
      - source     : 미지정이면 'telegram'(기존 호출부 무변경)
      - created_at : 미지정이면 지금 시각. **네이버 경로는 기사 발행시각을 넣는다** —
        created_at 은 news_pm_count(12시 이후)·get_news_heat(NOW() 기준 창)·news_guard 의
        오버나잇 창 기준이라, 30분 주기 수집기가 '수집 시각'을 넣으면 저녁 사이클 분이
        전부 오후 재료로 잡히고 창 분석이 오염된다.
    반환: 실제 삽입된 행 수.
    """
    if not rows:
        return 0
    now = datetime.now()
    payload = [{
        "ticker": r["ticker"],
        "company_name": r.get("company_name"),
        "headline": r.get("headline"),
        "source_url": r.get("source_url"),
        "channel_name": r.get("channel_name"),
        "published_at": r.get("published_at"),
        "source": r.get("source") or "telegram",
        "created_at": r.get("created_at") or now,
    } for r in rows]
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT IGNORE INTO news_mention
                (ticker, company_name, headline, source_url, channel_name,
                 published_at, source, created_at)
            VALUES (%(ticker)s, %(company_name)s, %(headline)s, %(source_url)s,
                    %(channel_name)s, %(published_at)s, %(source)s, %(created_at)s)
            """,
            payload,
        )
        inserted = cursor.rowcount
        conn.commit()
    return inserted


def get_today_news_count_by_stock(stock_code: str) -> int:
    """오늘 수집된 특정 종목의 뉴스 언급 건수 (created_at = 오늘)."""
    code = stock_code.split(".")[0].split("_")[0]
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE(){src_sql}
            """,
            (code, *src_params),
        )
        return int(cursor.fetchone()["cnt"])


def get_today_news_stats_by_stock(stock_code: str) -> dict:
    """오늘 뉴스 언급의 연구 라벨 집계 (closing_bet 이 daily_stock_report 에 저장).

    반환: {count, unique_count, pm_count, first_today, prior_avg}
      - count        : 오늘 총 언급 건수 (기존 get_today_news_count_by_stock 과 동일 기준)
      - unique_count : 헤드라인 정규화 dedup 고유 기사 수 (채널 복제 제거)
      - pm_count     : 12시 이후 언급 수 (종가베팅 신선도 — 장중 늦게 터진 재료)
      - first_today  : 직전 `_FIRST_TODAY_LOOKBACK_DAYS`일 내 언급 이력이 없으면 1
      - prior_avg    : 직전 7일 일평균 언급 수 (서프라이즈 배수의 분모). 오늘 언급 없으면 None
    """
    code = stock_code.split(".")[0].split("_")[0]
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT headline, created_at FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE(){src_sql}
            """,
            (code, *src_params),
        )
        today_rows = cursor.fetchall()
        if not today_rows:
            return {"count": 0, "unique_count": 0, "pm_count": 0,
                    "first_today": 0, "prior_avg": None}

        cursor.execute(
            f"""
            SELECT COUNT(*) AS prior_total,
                   SUM(created_at >= CURDATE() - INTERVAL 7 DAY) AS prior_7d
            FROM news_mention
            WHERE ticker = %s AND created_at < CURDATE()
              AND created_at >= CURDATE() - INTERVAL %s DAY{src_sql}
            """,
            (code, _FIRST_TODAY_LOOKBACK_DAYS, *src_params),
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
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT headline, source_url, channel_name, created_at
            FROM news_mention
            WHERE ticker = %s AND DATE(created_at) = CURDATE(){src_sql}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (code, *src_params, int(limit)),
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
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT headline, company_name, channel_name, created_at
            FROM news_mention
            WHERE ticker = %s AND created_at >= %s{src_sql}
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (code, since_dt, *src_params, int(limit)),
        )
        return cursor.fetchall()


def get_recent_news_by_stocks(
    stock_codes: list[str], days: int = 5
) -> dict[str, list[dict]]:
    """여러 종목의 최근 days 일(오늘 포함) 헤드라인을 **한 번의 쿼리**로 묶어 반환.

    재료 지속성 판정(core/news_material_judge)은 당일 헤드라인만으로는 `stage`(첫 발표인지
    후속 보도인지)를 알 수 없어 다일 룩백이 필요하다. 종목마다 따로 조회하면 유니버스
    전건 판정 시 쿼리가 종목 수만큼 늘어나므로 벌크로 받는다.

    반환: {code: [{"d": date, "headline": str, "created_at": datetime}, ...]}
          (종목별 created_at 오름차순 — 프롬프트 블록이 시간순이어야 stage 판정이 된다)
    """
    codes = [c.split(".")[0].split("_")[0] for c in stock_codes if c]
    if not codes:
        return {}
    placeholders = ", ".join(["%s"] * len(codes))
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT ticker, DATE(created_at) AS d, headline, created_at
            FROM news_mention
            WHERE ticker IN ({placeholders})
              AND created_at >= CURDATE() - INTERVAL %s DAY{src_sql}
            ORDER BY ticker, created_at ASC
            """,
            (*codes, int(max(0, days - 1)), *src_params),
        )
        out: dict[str, list[dict]] = {}
        for row in cursor.fetchall():
            out.setdefault(row["ticker"], []).append({
                "d": row["d"],
                "headline": row["headline"],
                "created_at": row["created_at"],
            })
        return out


def get_news_max_at_by_stocks(stock_codes: list[str]) -> dict[str, datetime]:
    """종목별 오늘 마지막 언급 시각 — 재료 판정 캐시 기준(news_judge_max_at 비교용).

    closing_bet 은 30분마다 재실행되므로 새 헤드라인이 없으면 LLM 을 다시 부르지 않는다
    (news_veto_verdict.news_max_at 선례).
    """
    codes = [c.split(".")[0].split("_")[0] for c in stock_codes if c]
    if not codes:
        return {}
    placeholders = ", ".join(["%s"] * len(codes))
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT ticker, MAX(created_at) AS max_at FROM news_mention
                 WHERE ticker IN ({placeholders})
                   AND DATE(created_at) = CURDATE(){src_sql}
                 GROUP BY ticker""",
            (*codes, *src_params),
        )
        return {r["ticker"]: r["max_at"] for r in cursor.fetchall() if r["max_at"]}


def get_news_days_by_stocks(
    stock_codes: list[str], start_date, end_date
) -> dict[str, list[dict]]:
    """여러 종목의 [start_date, end_date] 언급을 날짜·헤드라인만 벌크 조회.

    후속 재료 실현 채점(outcome_backfill 의 news_followup_days)용 — 행마다 창이 달라
    Python 에서 창을 자르므로 여기서는 넉넉한 구간을 한 번에 받는다.
    반환: {code: [{"d": date, "headline": str}, ...]}
    """
    codes = [c.split(".")[0].split("_")[0] for c in stock_codes if c]
    if not codes:
        return {}
    placeholders = ", ".join(["%s"] * len(codes))
    src_sql, src_params = _source_filter()
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT ticker, DATE(created_at) AS d, headline FROM news_mention
                 WHERE ticker IN ({placeholders})
                   AND DATE(created_at) BETWEEN %s AND %s{src_sql}""",
            (*codes, start_date, end_date, *src_params),
        )
        out: dict[str, list[dict]] = {}
        for row in cursor.fetchall():
            out.setdefault(row["ticker"], []).append(
                {"d": row["d"], "headline": row["headline"]}
            )
        return out


# 서프라이즈 배수의 분모 하한. 직전 7일 일평균이 이보다 작아도 1로 본다 —
# 이력이 없는 종목의 배수가 무한정 커지는 것을 막고, 값이 그대로 '오늘 건수'가 되게 한다.
_SURPRISE_FLOOR = 1.0


def get_news_heat(hours: int = 24, limit: int = 20) -> list[dict]:
    """최근 N시간 뉴스가 몰린 종목 순위 (프론트 '오늘 새로 뜬 재료' 카드용).

    **정렬은 건수가 아니라 자기 기저 대비 배수(surprise)다.** 건수 랭킹은 사실상 시총
    랭킹이라(실측 2026-07-29: 하이닉스 95·현대차 57·삼성전자 43건이 상단 고정) 매일 같은
    대형주만 보였다. 직전 7일 일평균으로 나누면 "평소 조용했는데 오늘 시끄러운 종목"이 올라온다.
    건수·기저는 함께 반환해 화면이 근거를 같이 보여줄 수 있게 한다.

    오늘 유니버스에 든 종목이면 재료 지속성 라벨(durability/catalyst/summary)을 함께 실어
    카드가 '무슨 재료인지'까지 보여줄 수 있게 한다(유니버스 밖 종목은 NULL).
    """
    src_sql, src_params = _source_filter()
    # 서브쿼리(기저)와 본 쿼리에 각각 별칭이 다른 같은 필터를 붙인다.
    prior_src = src_sql.replace(" AND source IN", " AND p.source IN")
    main_src = src_sql.replace(" AND source IN", " AND n.source IN")
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT n.ticker,
                   MAX(n.company_name) AS company_name,
                   COUNT(*) AS mention_count,
                   MAX(n.created_at) AS last_at,
                   (SELECT COUNT(*) FROM news_mention p
                     WHERE p.ticker = n.ticker
                       AND p.created_at < CURDATE()
                       AND p.created_at >= CURDATE() - INTERVAL 7 DAY{prior_src}) / 7 AS prior_avg,
                   MAX(r.news_durability) AS durability,
                   MAX(r.news_catalyst) AS catalyst,
                   MAX(r.news_summary) AS summary,
                   MAX(r.rank_no) AS rank_no
            FROM news_mention n
            LEFT JOIN daily_stock_report r
                   ON r.stock_code = n.ticker AND r.report_date = CURDATE()
            WHERE n.created_at >= NOW() - INTERVAL %s HOUR{main_src}
            GROUP BY n.ticker
            """,
            (*src_params, int(hours), *src_params),
        )
        results = cursor.fetchall()

    for row in results:
        if isinstance(row.get("last_at"), datetime):
            row["last_at"] = row["last_at"].isoformat()
        prior = float(row.get("prior_avg") or 0.0)
        row["prior_avg"] = round(prior, 2)
        row["surprise"] = round(int(row["mention_count"]) / max(prior, _SURPRISE_FLOOR), 1)
        row["in_universe"] = 1 if row.get("rank_no") is not None else 0
        row.pop("rank_no", None)

    results.sort(key=lambda r: (-r["surprise"], -r["mention_count"], r["last_at"] or ""))
    return results[:int(limit)]


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
