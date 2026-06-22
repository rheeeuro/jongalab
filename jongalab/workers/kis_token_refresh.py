"""한국투자증권(KIS) 액세스 토큰 매일 갱신 워커.

매일 1회 PM2 cron으로 실행해 새 토큰을 발급·저장한다(kis_token 단일행 UPSERT).
KIS 토큰은 ~24h 유효하며, 누락/만료 시 core.kis_client.ensure_token() 이
on-demand 로 재발급하므로 본 워커는 안전망(daily refresh) 역할이다.
"""
import logging
import sys

from core.logging_setup import setup_logging
from core.kis_client import KisRestClient

setup_logging()
logger = logging.getLogger("KisTokenRefresh")


def main() -> int:
    client = KisRestClient()
    try:
        client.get_access_token()
    except Exception as e:
        logger.error(f"KIS 토큰 발급 실패: {e}")
        return 1
    logger.info("KIS 토큰 갱신 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
