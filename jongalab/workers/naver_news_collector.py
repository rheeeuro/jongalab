"""네이버 증권 뉴스 수집 워커 — 유니버스·보유 종목의 당일 기사를 news_mention 에 멱등 적재한다.

[왜 필요한가]
유니버스 종목 중 뉴스 라벨을 받는 건 47%뿐이었다(2026-07-31 실측 18/38). 나머지 53%는
텔레그램 뉴스 채널이 그 종목 기사를 옮기지 않아서 생긴 공백이고, 채널을 늘려도 안 메워진다
— no_match 코퍼스 45건을 육안 분류하니 매칭 실패분 중 상장사 귀속이 가능한 건 9%뿐이고
나머지는 해외·정치·연예·거시라 애초에 종목 뉴스가 아니었다. 네이버 종목별 뉴스는
**종목코드로 조회하므로 사명 매칭이 없다** — 텔레그램 경로의 no_match 문제를 우회해 유니버스
커버리지가 크게 올라간다(실측: docs/history/news-pipeline.md).

[흐름] 1사이클(단발 프로세스, 스케줄러가 30분마다 spawn)
  1. 대상 종목 = 오늘 유니버스 ∪ 전거래일 유니버스 ∪ 보유 종목
     전거래일을 넣는 이유: 08:45 첫 사이클에는 오늘 유니버스가 아직 없다(closing_bet 08:30~).
     보유 종목을 넣는 이유: 밤사이·장중 악재는 아직 유니버스에 없어도 봐야 한다.
  2. 종목별 1페이지 조회 → **당일 기사만** 필터
  3. news_mention 에 INSERT IGNORE — (source_url, ticker) UNIQUE 로 재실행 멱등

[created_at 을 기사 발행시각으로 넣는다]
created_at 은 news_pm_count(12시 이후)·get_news_heat(NOW() 기준 창)·news_guard 오버나잇 창의
기준이다. 30분 주기 수집기가 '수집 시각'을 넣으면 저녁 사이클 분이 전부 오후 재료로 잡히고
창 분석이 오염된다. 그래서 발행시각(분 단위 정확)을 created_at·published_at 둘 다에 넣는다.

[소비 범위 — 텍스트만 반영, 카운트는 동결] (2026-08-05)
`source='naver'` 행은 **텍스트 게이트(NEWS_TEXT_SOURCES)에 포함**돼 재료 지속성 판정·뉴스
베토 판정·화면 헤드라인의 원자료가 된다. 이걸 연 이유는 지속성 라벨 커버리지가 유니버스의
30%(실측 8/4: 62행 중 18행)뿐이었고, 그 원인이 텔레그램 종목 커버리지 44% 였기 때문이다
(네이버는 97%).
**카운트 게이트(NEWS_COUNT_SOURCES)는 telegram 으로 동결한다** — news_count·prior_avg·
unique_count 는 소스를 늘리면 도입일에 계단식으로 튀고(네이버 2,800행/일 vs 텔레그램
500행/일, 헤드라인 중복 2%뿐) 그 표본을 `veto_bad_news`(live=자금 경로)가 쓴다.
→ live veto 의 **발동 조건(news_unique_count>=2)은 그대로**고 sentiment 판정 근거만 넓어진다.
  네이버 코퍼스에 대량으로 섞인 시세보도가 sentiment 를 끌어내리는 오탐 경로는 판정 코퍼스
  선별에서 걷어낸다(news_material_judge.select_headlines 의 is_price_report 필터).

[실패 안전] 조회 실패는 종목 단위로 건너뛰고 계속한다. 403/429(차단)만 사이클을 조기
종료한다 — 막힌 상태로 60종목을 계속 두드리면 차단이 길어진다. 수집 공백은 관측 전용
기간엔 무해하고, 승격 후에도 라벨 NULL = rule 미개입이다.

[cron] **매일** 08:45~20:45 매 30분(:15/:45) — closing_bet(:00/:30)·disclosure_collector(:20/:50)
와 어긋나게 둔다. 휴장일에도 도는 이유는 연휴 중 터진 재료가 재개장일 선정 시점에 라벨을
갖고 있어야 하기 때문이다(휴장일에도 종목 기사는 실재한다 — 근거: docs/history/news-pipeline.md).
휴장일엔 오늘 유니버스가 없으므로 대상은 전거래일 유니버스 ∪ 보유 종목이 된다.
단발 실행: uv run workers/naver_news_collector.py [--date YYYY-MM-DD] [--limit N] [--dry-run]
"""
import argparse
import logging
import time
from datetime import datetime

from core.config import (
    NAVER_NEWS_ENABLED, NAVER_NEWS_SLEEP_SEC, NEWS_COUNT_SOURCES, NEWS_TEXT_SOURCES,
)
from core.logging_setup import setup_logging
from core.naver_news_client import (
    SOURCE, NaverNewsBlocked, NaverNewsError, fetch_stock_news,
)
from core.repository.news import save_news_mentions
from core.repository.stock_report import (
    get_report_dates_before_today, get_stock_reports_by_date,
)
from core.repository.trading_position import get_open_positions

setup_logging()
logger = logging.getLogger("NaverNewsCollector")


def resolve_targets(date_str: str) -> dict[str, str]:
    """대상 종목 {코드: 이름}. 오늘 유니버스 + 전거래일 유니버스 + 보유 종목.

    전거래일 유니버스는 첫 사이클(오늘 리포트가 아직 없을 때)의 씨앗이다. 오늘 유니버스가
    채워지면 자연히 합집합이 되고, 30분 뒤 사이클에 새 종목이 따라 들어온다.
    """
    targets: dict[str, str] = {}
    for row in get_stock_reports_by_date(date_str, include_unselected=True):
        targets[row["stock_code"]] = row.get("stock_name") or ""

    # 오래된→최신 정렬이므로 직전 거래일은 마지막 원소다.
    prev_dates = [d for d in get_report_dates_before_today() if d < date_str]
    if prev_dates:
        for row in get_stock_reports_by_date(prev_dates[-1], include_unselected=True):
            targets.setdefault(row["stock_code"], row.get("stock_name") or "")

    try:
        for pos in get_open_positions():
            code = (pos.get("stk_cd") or "").split(".")[0].split("_")[0]
            if code:
                targets.setdefault(code, "")
    except Exception as e:
        # trading DB 조회 실패는 수집 자체를 막지 않는다(유니버스만으로 계속).
        logger.warning("보유 종목 조회 실패 — 유니버스만 수집: %s", e)
    return targets


def _to_rows(code: str, name: str, articles: list[dict], date_str: str) -> list[dict]:
    """클라이언트 반환 → news_mention 행. 당일 기사만 남긴다."""
    rows = []
    for a in articles:
        published_at = a["published_at"]
        if published_at.strftime("%Y-%m-%d") != date_str:
            continue
        rows.append({
            "ticker": code,
            "company_name": name or None,
            "headline": a["headline"],
            "source_url": a["source_url"],
            "channel_name": a["channel_name"],
            "published_at": published_at,
            "created_at": published_at,   # 라벨 창 기준 — 수집 시각이 아니다(모듈 주석 참고)
            "source": SOURCE,
            "body_preview": a.get("body_preview"),
        })
    return rows


def run(date_str: str, limit: int | None = None, dry_run: bool = False) -> int:
    if not NAVER_NEWS_ENABLED:
        logger.info("NAVER_NEWS_ENABLED=0 — 수집 건너뜀")
        return 0

    targets = resolve_targets(date_str)
    if not targets:
        logger.info("대상 종목 없음(%s 유니버스·보유 모두 비어있음) — 종료", date_str)
        return 0
    codes = list(targets)[:limit] if limit else list(targets)

    total_articles = 0
    inserted_total = 0
    covered: list[str] = []
    failed = 0
    blocked = False
    started = time.time()

    for code in codes:
        try:
            articles = fetch_stock_news(code)
        except NaverNewsBlocked as e:
            # 막힌 상태로 계속 두드리면 차단이 길어진다 — 남은 종목은 다음 주기에.
            logger.error("차단 응답 — 이번 사이클 중단(다음 주기 재시도): %s", e)
            blocked = True
            break
        except NaverNewsError as e:
            failed += 1
            logger.warning("조회 실패(건너뜀): %s", e)
            time.sleep(NAVER_NEWS_SLEEP_SEC)
            continue

        rows = _to_rows(code, targets[code], articles, date_str)
        total_articles += len(rows)
        if rows:
            covered.append(code)
            if not dry_run:
                try:
                    inserted_total += save_news_mentions(rows)
                except Exception as e:
                    failed += 1
                    logger.error("[%s] 적재 실패: %s", code, e)
        time.sleep(NAVER_NEWS_SLEEP_SEC)

    logger.info(
        "네이버 뉴스 수집 %s — 대상 %d종목 / 당일 기사 %d건 / 신규 적재 %d건 / "
        "커버 %d종목(%.0f%%) / 실패 %d / %.0fs%s",
        date_str, len(codes), total_articles, inserted_total, len(covered),
        len(covered) / max(len(codes), 1) * 100, failed, time.time() - started,
        " [dry-run]" if dry_run else "",
    )
    # 소비 게이트는 용도별로 둘이라 소스 하나가 '반영/미반영' 이진이 아니다 — 어느 쪽에
    # 들어가 있는지 매 사이클 남긴다(승격·동결 상태를 로그만 보고 알 수 있어야 한다).
    logger.info("소비 게이트 — 텍스트(재료·베토 판정) %s / 카운트(집계 라벨·룰) %s → "
                "source='%s' 는 텍스트 %s, 카운트 %s",
                list(NEWS_TEXT_SOURCES), list(NEWS_COUNT_SOURCES), SOURCE,
                "반영" if SOURCE in NEWS_TEXT_SOURCES else "미반영",
                "반영" if SOURCE in NEWS_COUNT_SOURCES else "미반영")
    # 차단은 다음 주기 재시도로 충분하지만, 반복되면 스케줄러 job_run 에 남도록 실패로 알린다.
    return 1 if blocked else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 증권 뉴스 수집 워커")
    parser.add_argument("--date", help="수집 일자 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--limit", type=int, help="대상 종목 수 제한(수동 점검용)")
    parser.add_argument("--dry-run", action="store_true", help="조회만 하고 저장하지 않음")
    args = parser.parse_args()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    return run(date_str, args.limit, args.dry_run)


if __name__ == "__main__":
    import sys

    # 거래일 가드 없음 — 휴장일 기사도 재개장일 선정 시점의 재료라 그날 안에 수집해야 한다
    # (당일 기사만 적재하는 구조라 다음 날 회차가 소급해 주지 않는다).
    sys.exit(main())
