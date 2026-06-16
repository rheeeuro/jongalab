"""종가베팅 사이클 청산 워커.

PM2 cron 으로 청산 시점(예: 익일 시초가/장중 특정 시각)에 실행:
  보유 포지션 → 청산 후보 판정 → 매도 집행.
첫 범위에서는 장중 상시 손절 감시(position_monitor) 대신 사이클 단위 청산만 한다.
"""
import sys
import logging

from core.logging_setup import setup_logging
from core.position_manager import PositionManager

setup_logging()
logger = logging.getLogger("Settle")


def main() -> int:
    logger.info("종가베팅 청산 시작")
    pm = PositionManager()
    positions = pm.open_positions()
    if not positions:
        logger.info("보유 포지션 없음 — 종료")
        return 0

    # TODO: 현재가 조회(kiwoom 데이터 서버) → 청산 후보 판정 → 매도 집행
    logger.warning("청산 로직 미구현(스켈레톤) — 보유 %d 종목", len(positions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
