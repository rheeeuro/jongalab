"""증권 섹션 뉴스 수집 워커 — 뉴스 탭 헤드라인의 원자료를 `sec_news` 에 멱등 적재한다.

[왜 필요한가]
뉴스 탭 헤드라인이 텔레그램 종합 속보 채널(`news_mention`)을 읽는 동안 주식과 무관한
기사가 화면에 올라왔다 — 2026-08-05 실측 14일 5,674기사 중 4.1%가 명백한 오탐이다
(`70대 남성 사망`→남성 004270 · `한화, 삼성 4-1 제압 3연패 탈출`→한화 000880 ·
`7월 소비자물가 2.8%↑(상보)`→상보 027580). 원인은 매처가 아니라 **모집단**이다.
그 채널은 주식 전용이 아닌데 저장 여부를 사명 매칭 하나로만 갈랐다.
네이버 증권 섹션 목록은 모집단이 이미 증권 기사라 야구·사건사고·연예가 구조적으로
들어오지 않는다 → 화면 소스를 통째로 이쪽으로 옮긴다.

[왜 기존 naver_news_collector 를 안 쓰는가]
그쪽은 **유니버스 62종목을 종목코드로 깊게** 훑어 재료 라벨 커버리지(92%)를 만드는
집계 경로다. 시황·환율·정책처럼 종목이 안 붙는 증권 기사는 거기 안 들어온다. 반대로
이 워커는 시장 전체를 얕게 훑고 종목 귀속이 부정확하다(사명 매칭). **둘은 대체재가
아니라 보완재**라서 워커도 적재처도 나눈다 — 합치면 한쪽 목적이 반드시 상한다.

[흐름] 1사이클(단발 프로세스, 스케줄러가 30분마다 spawn)
  1. 섹션 목록을 1페이지부터 순회 (최신순 20건/페이지)
  2. 기사마다 `match_companies` 로 종목 칩을 붙인다 — 화면 표시 전용이다
  3. `sec_news` 에 INSERT IGNORE (article_key UNIQUE → 재실행 멱등)
  4. **신규 0건인 페이지를 만나면 중단** — 그 뒤는 이미 다 가진 기사다(최신순 보장).
     상한은 SEC_NEWS_MAX_PAGES.

⚠️ **과거 날짜를 메울 땐 `--full` 을 붙인다.** 위 4번의 조기 종료는 30분 증분 전용이다 —
   그 날 앞부분을 이미 가진 상태로 뒷부분(=이른 시각 기사)을 채우려 하면 1페이지에서
   바로 멈춘다. `--full` 은 조기 종료를 끄고 `--pages` 까지 끝까지 훑는다.

[⚠️ '0건'을 정상으로 취급하지 않는다]
소스가 JSON API 가 아니라 HTML 목록이라, 네이버가 마크업을 바꾸면 파서가 **예외 없이
빈 리스트**를 돌려준다. 그대로 두면 "신규 0건 → 정상 종료"가 되어 화면이 조용히 빈다.
그래서 **1페이지에서 기사를 하나도 못 뽑으면 실패(exit 1)** 로 올려 job_run 에 남긴다.
휴장일에도 증권 섹션은 기사를 정상적으로 내보내므로 이 규칙은 매일 그대로 유효하다
(근거: docs/history/news-pipeline.md).

[created_at 이 아니라 published_at 이 기준이다]
화면 날짜 이동은 '그 날 난 기사'를 보여줘야 한다. 30분 주기 수집기가 수집 시각으로
날짜를 가르면 자정 직전 기사가 다음 날로 넘어간다.

[관측·표시 전용] `sec_news` 는 라벨·rule·veto·점수 어디에서도 읽지 않는다(sql/49).
끄면(SEC_NEWS_ENABLED=0) 뉴스 탭 헤드라인만 비고 나머지 파이프라인은 무영향이다.

수동 실행:
  uv run workers/sec_news_collector.py [--date YYYY-MM-DD] [--pages N] [--full] [--dry-run]
  과거 하루 전체 메우기: --date 2026-08-04 --pages 120 --full   (실측 하루 최대 ~60페이지)
"""
import argparse
import logging
import time
from datetime import datetime

from core.config import (
    SEC_NEWS_ENABLED, SEC_NEWS_MAX_PAGES, SEC_NEWS_SLEEP_SEC,
)
from core.logging_setup import setup_logging
from core.naver_news_client import (
    NaverNewsBlocked, NaverNewsError, fetch_section_news,
)
from core.news_matcher import match_companies
from core.repository.sec_news import save_sec_news

setup_logging()
logger = logging.getLogger("SecNewsCollector")

# source_url 끝 두 조각(officeId/articleId)이 곧 멱등키다 — URL 형식이 바뀌어도 안 흔들린다.
def _article_key(source_url: str) -> str:
    return "/".join(source_url.rstrip("/").split("/")[-2:])


def _to_row(article: dict) -> dict:
    """클라이언트 반환 → sec_news 행. 종목 칩은 표시 전용이라 매칭 실패해도 그냥 빈 목록."""
    return {
        "article_key": _article_key(article["source_url"]),
        "headline": article["headline"],
        "source_url": article["source_url"],
        "press": article["channel_name"],
        "published_at": article["published_at"],
        "tickers": match_companies(article["headline"]),
    }


def run(date_str: str, max_pages: int, dry_run: bool = False,
        full: bool = False) -> int:
    if not SEC_NEWS_ENABLED:
        logger.info("SEC_NEWS_ENABLED=0 — 수집 건너뜀")
        return 0

    fetched = 0
    inserted_total = 0
    pages_read = 0
    started = time.time()

    for page in range(1, max_pages + 1):
        try:
            articles = fetch_section_news(date_str, page)
        except NaverNewsBlocked as e:
            # 막힌 상태로 계속 두드리면 차단이 길어진다 — 남은 페이지는 다음 주기에.
            logger.error("차단 응답 — 이번 사이클 중단(다음 주기 재시도): %s", e)
            return 1
        except NaverNewsError as e:
            logger.warning("페이지 조회 실패(중단, 다음 주기 재시도): %s", e)
            break

        pages_read += 1
        if not articles:
            if page == 1:
                # 파서 파손과 구분이 안 되는 유일한 지점이다 — 실패로 올린다(모듈 주석 참고).
                logger.error(
                    "%s 1페이지에서 기사를 하나도 못 뽑았다 — 목록 HTML 구조 변경 의심"
                    "(naver_news_client._SUBJECT_RE / _WDATE_RE 확인)", date_str)
                return 1
            break

        fetched += len(articles)
        rows = [_to_row(a) for a in articles]
        if dry_run:
            for r in rows[:3]:
                logger.info("  [dry-run] %s | %s | %s",
                            r["published_at"], r["press"], r["headline"][:60])
        else:
            try:
                inserted = save_sec_news(rows)
            except Exception as e:
                logger.error("p%d 적재 실패(중단): %s", page, e)
                return 1
            inserted_total += inserted
            # 최신순이라 신규가 없으면 그 뒤는 전부 이미 가진 기사다 — 증분 사이클의 종료 조건.
            # 과거 날짜 보정(--full)에서는 반대로 '앞부분만 갖고 뒷부분이 빈' 상태가 정상이라
            # 이 규칙이 1페이지에서 순회를 죽인다.
            if inserted == 0 and not full:
                break
        time.sleep(SEC_NEWS_SLEEP_SEC)

    logger.info(
        "증권 섹션 뉴스 수집 %s — %d페이지 / 조회 %d건 / 신규 적재 %d건 / %.0fs%s",
        date_str, pages_read, fetched, inserted_total, time.time() - started,
        " [dry-run]" if dry_run else "",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="증권 섹션 뉴스 수집 워커(뉴스 탭 표시용)")
    parser.add_argument("--date", help="수집 일자 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--pages", type=int, help="최대 페이지 수(기본: SEC_NEWS_MAX_PAGES)")
    parser.add_argument("--full", action="store_true",
                        help="신규 0건 조기 종료를 끄고 --pages 까지 끝까지 훑는다(과거 날짜 보정용)")
    parser.add_argument("--dry-run", action="store_true", help="조회만 하고 저장하지 않음")
    args = parser.parse_args()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    return run(date_str, args.pages or SEC_NEWS_MAX_PAGES, args.dry_run, args.full)


if __name__ == "__main__":
    import sys

    # 거래일 가드 없음 — 휴장일에도 증권 섹션 기사는 정상적으로 나오고(그래서 '1페이지 0건'
    # 실패 규칙도 그대로 유효하다), 연휴 기사가 비면 뉴스 탭이 재개장일에 통째로 빈다.
    sys.exit(main())
