"""포지션 정합성 워커.

PM2 cron 으로 장 마감 후 실행:
  키움 계좌 잔고(kt00018) ↔ 로컬 position 테이블 대조 → drift 감지·보정·알림.
자동매매에서 로컬 상태와 실계좌가 어긋나면 가장 위험하므로 매일 확인한다.
"""
import sys
import logging

from core.logging_setup import setup_logging
from core.kiwoom_order_client import KiwoomOrderClient, TokenUnavailable
from core.position_manager import PositionManager

setup_logging()
logger = logging.getLogger("Reconcile")


def main() -> int:
    logger.info("포지션 정합성 점검 시작")
    pm = PositionManager()
    client = KiwoomOrderClient()

    try:
        balance = client.get_balance()
    except TokenUnavailable as e:
        logger.error("토큰 없음 — 정합성 점검 불가: %s", e)
        return 1
    except Exception as e:
        logger.error("잔고 조회 실패: %s", e)
        return 1

    local = pm.open_positions()
    # TODO: balance vs local 비교 → drift 종목 로깅/알림/보정
    logger.info("로컬 %d 종목 / 키움 잔고 응답 수신 — 대조 로직 미구현(스켈레톤)", len(local))
    _ = balance
    return 0


if __name__ == "__main__":
    sys.exit(main())
