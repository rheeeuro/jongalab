"""키움 액세스 토큰 매일 갱신 워커
매일 07:00 KST에 PM2 cron으로 실행:
  1) DB에 저장된 기존 토큰 폐기 (au10002) — 실패해도 무시
  2) 새 토큰 발급 (au10001) → DB UPSERT
"""
import logging
import sys

from core.logging_setup import setup_logging
from core.kiwoom_api import KiwoomConfig, KiwoomRestAPI
from core.repository import kiwoom_token as token_repo

setup_logging()
logger = logging.getLogger("KiwoomTokenRefresh")


def main() -> int:
    api = KiwoomRestAPI(KiwoomConfig())

    # 1) 기존 토큰 로드 후 폐기 시도
    existing = None
    try:
        existing = token_repo.get_token()
    except Exception as e:
        logger.warning(f"DB에서 기존 토큰 조회 실패: {e}")

    if existing and existing.get("access_token"):
        api.cfg.ACCESS_TOKEN = existing["access_token"]
        api.revoke_access_token()  # 실패해도 내부에서 warn만 남김
    else:
        logger.info("기존 토큰 없음 — 폐기 단계 스킵")

    # 2) 새 토큰 발급 + DB 저장 (get_access_token 내부에서 save_token 호출)
    try:
        api.get_access_token()
    except Exception as e:
        logger.error(f"신규 토큰 발급 실패: {e}")
        return 1

    logger.info("키움 토큰 갱신 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
