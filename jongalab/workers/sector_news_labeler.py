"""미매칭 뉴스 코퍼스에 섹터·거시 라벨을 붙이는 워커 — **관측 전용(점수·시드·veto 무영향)**.

`news_matcher` 가 사명을 못 찾아 버린 헤드라인은 `content_skip(platform='news',
reason='no_match')` 에 쌓인다(2026-07-30~). 이 워커가 그 코퍼스를 읽어
`news_sector_label` 에 **섹터 + 방향** 라벨을 적재한다. 목적은 오직 검정 표본 축적이다 —
왜 지금 소비하지 않는지(사전검정에서 섹터 뉴스 '건수' 축이 t=+0.16 무신호)는 sql/45 주석.

실행은 목적이 다른 두 종류다(판정·적재 경로는 하나 — 라벨 정의가 갈라지지 않게):
  · **백로그 소화**(매일 20:30, 상한 NEWS_SECTOR_MAX_ROWS) — 오래된 것부터. 표본의 연속성이 목적.
  · **매수 전 전량 소화**(평일 14:30·19:00, `--since-today --newest-first`) — 그날 00시 이후
    미라벨 기사를 **전부**, 최신부터. KRX 15:20 / NXT 19:50 매수 판단 시점에 **그날 나온 거시·섹터
    기사가 라벨을 갖고 있게** 하는 것이 목적이다. 20:30 실행만 있으면 라벨은 언제나 매수 뒤에
    생겨, 뉴스 축은 검정조차 할 수 없다(사후에만 존재하는 데이터).
    상한은 하루치(1,700~2,000건)를 덮는 안전값이고, 조회가 상한에 닿으면 경고를 남긴다 —
    상한 포화는 '그날 전량'이라는 이 실행의 전제가 깨졌다는 뜻이다(경위: docs/history/news-pipeline.md).
    ⚠️ 라벨은 여전히 **관측 전용**이다 — 이 실행이 추가돼도 시드·점수·veto 는 읽지 않는다.

흐름:
  1. 라벨 없는 미매칭 헤드라인을 순서(오래된 것/최신)대로 NEWS_SECTOR_MAX_ROWS 건 조회
  2. 발행처 말머리·URL 제거 → 산업·정책·거시 어휘 프리필터(core/sector_news.is_topical)
  3. 프리필터 탈락분은 **LLM 없이 scope='무관' 으로 즉시 적재** — 안 적재하면 다음 실행에
     같은 행이 또 조회돼 백로그가 영원히 안 줄고, 프리필터 통과율도 못 잰다
  4. 통과분만 OpenAI 벌크 판정(core/sector_news.judge_headlines) → 적재
  5. scope×sector 분포 요약 로그(육안 감사 진입점)

실패 안전: LLM 실패 배치는 **적재하지 않고** 넘어간다 → 다음 실행에 자연 재시도(멱등 PK).
백로그가 크면 여러 날에 걸쳐 소화된다(상한이 하루 처리량). 수동 소화는 `--limit` 로 올린다.

수동 실행:
  uv run workers/sector_news_labeler.py --dry-run        # 프리필터 통과율만 확인(LLM 미호출)
  uv run workers/sector_news_labeler.py --limit 3000     # 백로그 일괄 소화
  uv run workers/sector_news_labeler.py --since-today --newest-first   # 그날 분량만(매수 전)
"""
import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, time as dtime

from core.config import (
    NEWS_SECTOR_ENABLED,
    NEWS_SECTOR_BATCH_SIZE,
    NEWS_SECTOR_MAX_ROWS,
    OPENAI_MODEL,
)
from core.logging_setup import setup_logging
from core.repository import news_sector as news_sector_repo
from core.sector_news import clean_headline, is_topical, judge_headlines

setup_logging()
logger = logging.getLogger("SectorNewsLabeler")


def _row(src: dict, headline: str, labels: dict | None, model: str | None) -> dict:
    """저장 행 1개. labels 가 None 이면 프리필터 탈락(무관, 방향 미판정)."""
    return {
        "external_id": src["external_id"],
        "news_at": src["created_at"],
        "scope": labels["scope"] if labels else "무관",
        "sector": labels["sector"] if labels else None,
        "sentiment": labels["sentiment"] if labels else None,
        "headline": headline,
        "reason": labels["reason"] if labels else "프리필터: 산업·정책·거시 어휘 없음",
        "model": model,
    }


def run(limit: int, batch_size: int, dry_run: bool = False,
        newest_first: bool = False, since_today: bool = False) -> int:
    """1회 실행. 반환: 적재한 라벨 행 수(dry-run 은 0).

    newest_first: 최신 기사부터 라벨한다(매수 전 실행용). 기본 False = 오래된 것부터(백로그 소화).
    since_today: 그날 00시 이후 기사로 범위를 좁힌다(매수 전 실행용) — 백로그가 밀려도 오늘치가
      상한을 두고 백로그와 경쟁하지 않게 한다.
    """
    since = datetime.combine(datetime.now().date(), dtime.min) if since_today else None
    rows = news_sector_repo.get_unlabeled_headlines(limit, since=since, newest_first=newest_first)
    if not rows:
        logger.info("라벨 대상 미매칭 뉴스 없음 — 종료")
        return 0
    logger.info("조회 범위: %s / 순서: %s (%s ~ %s)",
                "오늘 00시 이후" if since_today else "전체 백로그",
                "최신부터" if newest_first else "오래된 것부터",
                rows[0]["created_at"], rows[-1]["created_at"])
    if len(rows) >= limit:
        # 상한 포화 = 조회 범위 일부가 이번 실행에서 잘렸다. 매수 전 실행에선 '그날 전량'이라는
        # 전제가 깨진 것이라 뉴스 톤 축의 표본 정의가 조용히 달라진다.
        logger.warning("상한 %d 포화 — 잘린 기사가 있다. 매수 전 실행이면 그날 전량 전제가 깨진다", limit)

    topical: list[dict] = []      # LLM 판정 대상 {idx, headline, src}
    skipped: list[dict] = []      # 프리필터 탈락 저장 행
    for i, src in enumerate(rows):
        headline = clean_headline(src.get("title"))
        if not headline:
            continue
        if is_topical(headline):
            topical.append({"idx": i, "headline": headline, "src": src})
        else:
            skipped.append(_row(src, headline, None, None))

    pass_rate = len(topical) / max(1, len(topical) + len(skipped)) * 100
    logger.info("조회 %d건 → 프리필터 통과 %d건(%.1f%%), 탈락 %d건",
                len(rows), len(topical), pass_rate, len(skipped))

    if dry_run:
        for it in topical[:30]:
            logger.info("  [통과] %s", it["headline"][:100])
        return 0

    saved = news_sector_repo.save_labels(skipped)

    if topical:
        labels = judge_headlines(
            [{"idx": it["idx"], "headline": it["headline"]} for it in topical],
            batch_size,
        )
        # 판정이 없는 항목은 저장하지 않는다 — 다음 실행에 재시도(멱등 PK 가 중복을 막는다).
        judged = [_row(it["src"], it["headline"], labels[it["idx"]], OPENAI_MODEL)
                  for it in topical if it["idx"] in labels]
        saved += news_sector_repo.save_labels(judged)
        if len(judged) < len(topical):
            logger.warning("판정 누락 %d건 — 다음 실행에 재시도", len(topical) - len(judged))

        dist = Counter((r["scope"], r["sector"]) for r in judged)
        for (scope, sector), cnt in dist.most_common(12):
            logger.info("  %s%s: %d건", scope, f"/{sector}" if sector else "", cnt)

    logger.info("섹터 뉴스 라벨 적재 %d건 (관측 전용 — 점수·시드 무영향)", saved)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="미매칭 뉴스 섹터·거시 라벨 워커")
    parser.add_argument("--limit", type=int, default=NEWS_SECTOR_MAX_ROWS,
                        help=f"1회 처리 상한 (기본 {NEWS_SECTOR_MAX_ROWS})")
    parser.add_argument("--batch-size", type=int, default=NEWS_SECTOR_BATCH_SIZE,
                        help=f"LLM 1회 호출 헤드라인 수 (기본 {NEWS_SECTOR_BATCH_SIZE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="프리필터 통과율만 확인(LLM 미호출·미적재)")
    parser.add_argument("--newest-first", action="store_true",
                        help="최신 기사부터 라벨(매수 전 실행용). 기본은 오래된 것부터(백로그 소화)")
    parser.add_argument("--since-today", action="store_true",
                        help="그날 00시 이후 기사만(매수 전 실행용). 기본은 전체 백로그")
    args = parser.parse_args()

    if not NEWS_SECTOR_ENABLED:
        logger.info("NEWS_SECTOR_ENABLED=0 — 비활성")
        return 0

    run(args.limit, args.batch_size, args.dry_run, args.newest_first, args.since_today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
