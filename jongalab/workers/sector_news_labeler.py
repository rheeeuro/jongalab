"""미매칭 뉴스 코퍼스에 섹터·거시 라벨을 붙이는 워커 — **관측 전용(점수·시드·veto 무영향)**.

`news_matcher` 가 사명을 못 찾아 버린 헤드라인은 `content_skip(platform='news',
reason='no_match')` 에 쌓인다(2026-07-30~). 이 워커가 그 코퍼스를 읽어
`news_sector_label` 에 **섹터 + 방향** 라벨을 적재한다. 목적은 오직 검정 표본 축적이다 —
왜 지금 소비하지 않는지(사전검정에서 섹터 뉴스 '건수' 축이 t=+0.16 무신호)는 sql/45 주석.

흐름 (하루 1회, 평일 20:30):
  1. 라벨 없는 미매칭 헤드라인을 **오래된 것부터** NEWS_SECTOR_MAX_ROWS 건 조회
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
"""
import argparse
import logging
import sys
from collections import Counter

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


def run(limit: int, batch_size: int, dry_run: bool = False) -> int:
    """1회 실행. 반환: 적재한 라벨 행 수(dry-run 은 0)."""
    rows = news_sector_repo.get_unlabeled_headlines(limit)
    if not rows:
        logger.info("라벨 대상 미매칭 뉴스 없음 — 종료")
        return 0

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
    args = parser.parse_args()

    if not NEWS_SECTOR_ENABLED:
        logger.info("NEWS_SECTOR_ENABLED=0 — 비활성")
        return 0

    run(args.limit, args.batch_size, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
