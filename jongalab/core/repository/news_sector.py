"""미매칭 뉴스 섹터·거시 라벨 데이터 접근 (news_sector_label).

workers/sector_news_labeler.py 가 `content_skip(platform='news', reason='no_match')` 코퍼스를
읽어 라벨을 upsert 한다. **관측 전용 테이블이라 소비 경로(점수·시드·veto)는 없다** —
조회 함수는 검정·감사용 집계 하나뿐이고, live 경로에서 이 모듈을 import 하지 말 것
(그 순간 관측 전용이라는 성질이 조용히 깨진다. 근거는 sql/45 주석).
"""
from datetime import datetime

from core.db import get_db


def get_unlabeled_headlines(limit: int, since: datetime | None = None) -> list[dict]:
    """아직 라벨이 없는 미매칭 뉴스 헤드라인 (오래된 것부터).

    오래된 것부터 주는 이유: 백로그를 며칠에 걸쳐 소화할 때 창이 앞에서부터 메워져야
    '연속된 기간의 표본'이 된다(최신부터 먹으면 구멍 뚫린 표본이 남는다).
    """
    params: list = []
    where = ""
    if since is not None:
        where = " AND s.created_at >= %s"
        params.append(since)
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT s.external_id, s.title, s.created_at
            FROM content_skip s
            LEFT JOIN news_sector_label l ON l.external_id = s.external_id
            WHERE s.platform = 'news' AND s.reason = 'no_match'
              AND s.title IS NOT NULL AND l.external_id IS NULL{where}
            ORDER BY s.created_at ASC
            LIMIT %s
            """,
            (*params, int(limit)),
        )
        return cursor.fetchall()


def save_labels(rows: list[dict]) -> int:
    """라벨 일괄 저장 (external_id 중복은 무시 — 재실행·백필 멱등). 삽입 행 수 반환.

    rows 항목: {external_id, news_at, scope, sector, sentiment, headline, reason, model}
    """
    if not rows:
        return 0
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT IGNORE INTO news_sector_label
                (external_id, news_at, scope, sector, sentiment, headline, reason, model)
            VALUES (%(external_id)s, %(news_at)s, %(scope)s, %(sector)s,
                    %(sentiment)s, %(headline)s, %(reason)s, %(model)s)
            """,
            rows,
        )
        inserted = cursor.rowcount
        conn.commit()
    return inserted


def get_label_summary(days: int = 7) -> list[dict]:
    """최근 N일 라벨 분포 (scope×sector 건수·평균 방향) — 워커 로그와 육안 감사용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT scope, sector, COUNT(*) AS cnt, ROUND(AVG(sentiment), 1) AS avg_sentiment
            FROM news_sector_label
            WHERE news_at >= CURDATE() - INTERVAL %s DAY
            GROUP BY scope, sector
            ORDER BY cnt DESC
            """,
            (int(days),),
        )
        return cursor.fetchall()
