"""네이버 증권 뉴스 수집 워커 — 유니버스·보유 종목의 당일 기사를 news_mention 에 멱등 적재한다.

[왜 필요한가]
유니버스 종목 중 뉴스 라벨을 받는 건 47%뿐이었다(2026-07-31 실측 18/38). 나머지 53%는
텔레그램 뉴스 채널이 그 종목 기사를 옮기지 않아서 생긴 공백이고, 채널을 늘려도 안 메워진다
— no_match 코퍼스 45건을 육안 분류하니 매칭 실패분 중 상장사 귀속이 가능한 건 9%뿐이고
나머지는 해외·정치·연예·거시라 애초에 종목 뉴스가 아니었다. 네이버 종목별 뉴스는
**종목코드로 조회하므로 사명 매칭이 없다** — 실측 커버리지 92%(35/38), 신규 확보 17종목.

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

[관측 전용 — 지금은 라벨·룰·veto 에 일절 영향 없다]
적재하는 source='naver' 행은 config.NEWS_ACTIVE_SOURCES(기본 'telegram')에서 빠져 있어
repository 조회가 전부 걸러낸다. 소스를 늘리면 집계 라벨이 계단식으로 튀고(실측 네이버
562행 vs 텔레그램 273행, 헤드라인 중복 2%뿐이라 상쇄 없이 순증) news_unique_count 를 쓰는
rule 3종 중 `veto_bad_news` 가 live(자금 경로)라, 2~3주 병행 관측 후 .env 로 승격한다.
승격 시 함께 할 일은 sql/44 주석에 적어뒀다.

[실패 안전] 조회 실패는 종목 단위로 건너뛰고 계속한다. 403/429(차단)만 사이클을 조기
종료한다 — 막힌 상태로 60종목을 계속 두드리면 차단이 길어진다. 수집 공백은 관측 전용
기간엔 무해하고, 승격 후에도 라벨 NULL = rule 미개입이다.

[cron] 평일 08:45~20:45 매 30분(:15/:45) — closing_bet(:00/:30)·disclosure_collector(:20/:50)
와 어긋나게 둔다.
단발 실행: uv run workers/naver_news_collector.py [--date YYYY-MM-DD] [--limit N] [--dry-run]
"""
import argparse
import logging
import time
from datetime import datetime

from core.config import (
    NAVER_NEWS_ENABLED, NAVER_NEWS_SLEEP_SEC, NEWS_ACTIVE_SOURCES,
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
    if SOURCE not in NEWS_ACTIVE_SOURCES:
        logger.info("관측 전용 — source='%s' 는 NEWS_ACTIVE_SOURCES%s 에서 제외돼 "
                    "라벨·룰·veto 에 반영되지 않는다", SOURCE, list(NEWS_ACTIVE_SOURCES))
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

    from core.market_calendar import exit_if_not_trading_day

    # 휴장일엔 종가베팅이 안 돌아 유니버스도 없고 종목 기사도 거의 없다.
    # --date 로 수동 점검할 땐 거래일 가드를 건너뛴다(disclosure_collector 선례).
    if "--date" not in sys.argv:
        exit_if_not_trading_day()
    sys.exit(main())
