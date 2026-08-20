"""증권 섹션 뉴스 데이터 접근 (sec_news) — **표시 전용 계층**.

`news_mention`(집계 원자료)과 의도적으로 분리된 테이블이다. 왜 나눴는지는 sql/49 주석에
있고, 여기서 반드시 지킬 규칙은 하나다:

⚠️ **이 모듈은 라벨·rule·veto·점수 경로에서 import 하지 않는다.**
   읽는 순간 '표시 전용'이라는 성질이 조용히 깨지고, `config.NEWS_COUNT_SOURCES`/`NEWS_TEXT_SOURCES` 게이트(sql/44)가
   지키던 게이트를 우회하는 두 번째 뉴스 유입로가 생긴다. 재료 집계가 필요하면
   `repository/news.py` 를 쓴다 — 그쪽은 소스 필터를 전부 통과한다.

news_mention 과 달리 **기사 1행**이라 그 날 기사 수가 곧 행 수다
(news_mention 은 '헤드라인 × 종목' 이라 `get_news_stream` 이 파이썬에서 다시 접어야 했다).
"""
import json
from datetime import datetime

from core.db import get_db


def save_sec_news(rows: list[dict]) -> int:
    """섹션 기사를 일괄 저장 (article_key 중복은 무시). 반환: 실제 삽입된 행 수.

    rows 항목: {article_key, headline, source_url, press, published_at, tickers}
      - tickers: [{"ticker","name"}] 또는 None. 화면 종목 칩 전용이다.
    30분 주기 재수집이 같은 기사를 계속 다시 보므로 INSERT IGNORE 로 멱등을 잡는다 —
    호출부(sec_news_collector)는 이 반환값(신규 0건)을 페이지 순회 종료 신호로도 쓴다.
    """
    if not rows:
        return 0
    payload = [{
        "article_key": r["article_key"],
        "headline": r["headline"],
        "source_url": r["source_url"],
        "press": r.get("press"),
        "published_at": r["published_at"],
        "tickers": json.dumps(r.get("tickers") or [], ensure_ascii=False),
    } for r in rows]
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT IGNORE INTO sec_news
                (article_key, headline, source_url, press, published_at, tickers)
            VALUES (%(article_key)s, %(headline)s, %(source_url)s, %(press)s,
                    %(published_at)s, %(tickers)s)
            """,
            payload,
        )
        inserted = cursor.rowcount
        conn.commit()
    return inserted


def get_sec_news_day(
    date: str,
    q: str | None = None,
    ticker: str | None = None,
    cap: int = 2000,
) -> list[dict]:
    """그 날 증권 기사를 **필터 적용해 전부** 최신순 반환 (뉴스 탭 헤드라인 스트림).

    페이징을 SQL 에서 하지 않는다 — 화면이 시세 기사를 기본으로 숨기고 그 판별은 파이썬
    정규식(`is_price_report`)이라 SQL 이 세지 못한다. LIMIT 을 걸면 총계·'더 보기' 카운터·
    화면 건수가 서로 다른 수가 된다. 하루 ~1,000건이라 한 날을 통째로 읽어도 부담이 없고,
    그러면 세 숫자가 같은 모집단에서 나온다. 페이지 자르기는 호출부(라우터)가 한다.

    `q` 는 제목 부분 일치, `ticker` 는 종목 칩(JSON) 포함 여부다. `cap` 은 폭주 방어용 상한.

    목록 항목은 `get_news_stream` 과 **같은 shape** 이라 화면(NewsStream)·타입
    (NewsStreamItem)은 소스가 바뀐 걸 모른다:
      {headline, source_url, channel_name, created_at(ISO), stocks: [{ticker, name}]}
    `channel_name` 에 언론사를, `created_at` 에 발행 시각을 싣는다 — 화면이 이미 그 두
    필드를 발행처·시각으로 읽고 있다(lib/news.ts splitHeadlineMeta).
    """
    where = ["DATE(published_at) = %s"]
    params: list = [date]
    if q and q.strip():
        where.append("headline LIKE %s")
        params.append(f"%{_escape_like(q.strip())}%")
    if ticker and ticker.strip():
        # tickers 는 [{"ticker","name"}] JSON 이라 종목코드 문자열이 그대로 들어 있다.
        where.append("tickers LIKE %s")
        params.append(f'%"{_escape_like(ticker.strip())}"%')

    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT headline, source_url, press, published_at, tickers
                 FROM sec_news
                WHERE {" AND ".join(where)}
                ORDER BY published_at DESC, id DESC
                LIMIT %s""",
            (*params, int(cap)),
        )
        rows = cursor.fetchall()

    out = []
    for row in rows:
        published_at = row["published_at"]
        # tickers 는 JSON 컬럼이지만 커넥터 설정에 따라 str 로 오기도 한다 — 양쪽을 받는다.
        raw = row.get("tickers")
        if isinstance(raw, (str, bytes, bytearray)):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        out.append({
            "headline": row["headline"],
            "source_url": row["source_url"],
            "channel_name": row["press"],
            "created_at": published_at.isoformat()
                          if isinstance(published_at, datetime) else published_at,
            "stocks": raw if isinstance(raw, list) else [],
        })
    return out


def _escape_like(value: str) -> str:
    """LIKE 패턴 이스케이프 — 사용자 검색어의 `%`·`_` 가 와일드카드로 새지 않게."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def delete_old_sec_news(days: int = 30) -> int:
    """N일 이전 섹션 기사 삭제 (cleanup_content 워커가 호출). 삭제 행 수 반환.

    집계에 안 쓰이므로 잘려도 표본이 상하지 않는다 — 화면이 빈 목록으로 degrade 할 뿐이다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM sec_news WHERE published_at < NOW() - INTERVAL %s DAY",
            (int(days),),
        )
        deleted = cursor.rowcount
        conn.commit()
    return deleted
