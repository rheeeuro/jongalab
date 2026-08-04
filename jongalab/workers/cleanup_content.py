"""오래된 콘텐츠 분석 데이터 정리 워커 (매일 1회 cron).

content_analysis 는 최근 데이터(대시보드 7일/통계 24시간/오늘)만 조회하므로
3개월이 지난 행은 보관 가치가 없다. 매일 비대화 방지용으로 일괄 삭제한다.
"""
import logging
import sys

from core.config import NEWS_RETENTION_DAYS
from core.logging_setup import setup_logging
from core.repository import (
    delete_old_content_analysis,
    delete_old_content_skips,
    delete_old_analysis_fails,
    delete_old_news_mentions,
    delete_old_sec_news,
)

setup_logging()
logger = logging.getLogger("CleanupContent")

RETENTION_MONTHS = 3
# 뉴스 언급 보존일은 config.NEWS_RETENTION_DAYS(기본 30) — 네이버 병행 검증이 원자료에서
# "텔레그램만 vs 네이버 포함" 을 소급 재계산하는 방식이라 14일이면 검증 창이 잘린다.


def main() -> int:
    rc = 0
    try:
        deleted = delete_old_content_analysis(RETENTION_MONTHS)
        logger.info(f"콘텐츠 정리 완료: {RETENTION_MONTHS}개월 이전 {deleted}건 삭제")
    except Exception as e:
        logger.error(f"콘텐츠 정리 실패: {e}")
        rc = 1
    try:
        news_deleted = delete_old_news_mentions(NEWS_RETENTION_DAYS)
        logger.info(f"뉴스 언급 정리 완료: {NEWS_RETENTION_DAYS}일 이전 {news_deleted}건 삭제")
    except Exception as e:
        logger.error(f"뉴스 언급 정리 실패: {e}")
        rc = 1
    try:
        # 뉴스 탭 표시용 원자료(sec_news). 집계에 안 쓰이므로 잘려도 표본이 상하지 않는다 —
        # 같은 보존일을 쓰는 건 두 계층의 화면 날짜 이동 범위를 맞추기 위해서다.
        sec_deleted = delete_old_sec_news(NEWS_RETENTION_DAYS)
        logger.info(f"증권 섹션 뉴스 정리 완료: {NEWS_RETENTION_DAYS}일 이전 {sec_deleted}건 삭제")
    except Exception as e:
        logger.error(f"증권 섹션 뉴스 정리 실패: {e}")
        rc = 1
    try:
        skip_deleted = delete_old_content_skips(RETENTION_MONTHS)
        logger.info(f"스킵 기록 정리 완료: {RETENTION_MONTHS}개월 이전 {skip_deleted}건 삭제")
    except Exception as e:
        logger.error(f"스킵 기록 정리 실패: {e}")
        rc = 1
    try:
        fail_deleted = delete_old_analysis_fails(RETENTION_MONTHS)
        logger.info(f"분석 타임아웃 카운터 정리 완료: {RETENTION_MONTHS}개월 이전 {fail_deleted}건 삭제")
    except Exception as e:
        logger.error(f"분석 타임아웃 카운터 정리 실패: {e}")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
