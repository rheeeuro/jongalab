"""오래된 콘텐츠 분석 데이터 정리 워커 (매일 1회 cron).

content_analysis 는 최근 데이터(대시보드 7일/통계 24시간/오늘)만 조회하므로
3개월이 지난 행은 보관 가치가 없다. 매일 비대화 방지용으로 일괄 삭제한다.
"""
import logging
import sys

from core.logging_setup import setup_logging
from core.repository import delete_old_content_analysis

setup_logging()
logger = logging.getLogger("CleanupContent")

RETENTION_MONTHS = 3


def main() -> int:
    try:
        deleted = delete_old_content_analysis(RETENTION_MONTHS)
    except Exception as e:
        logger.error(f"콘텐츠 정리 실패: {e}")
        return 1
    logger.info(f"콘텐츠 정리 완료: {RETENTION_MONTHS}개월 이전 {deleted}건 삭제")
    return 0


if __name__ == "__main__":
    sys.exit(main())
