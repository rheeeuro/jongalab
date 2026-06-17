"""종가베팅 사이클 청산 워커.

PM2 cron 으로 청산 시점(예: 익일 시초가 09:05)에 실행:
  보유 포지션 전량을 현재가로 매도 집행(시초가 청산). paper 는 즉시 체결 시뮬레이션.
첫 범위에서는 장중 상시 손절 감시 대신 사이클 단위 전량 청산만 한다.
"""
import sys
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.repository import position as position_repo

setup_logging()
logger = logging.getLogger("Settle")


def main() -> int:
    trade_date = datetime.now().strftime("%Y%m%d")
    logger.info("종가베팅 청산 시작 (거래일 %s)", trade_date)

    positions = position_repo.get_open_positions()
    if not positions:
        logger.info("보유 포지션 없음 — 종료")
        return 0

    engine = ExecutionEngine()
    for p in positions:
        stk_cd, qty = p["stk_cd"], p["qty"]
        try:
            price = engine.data.get_current_price(stk_cd)
            if price <= 0:
                logger.warning("현재가 조회 실패 — 청산 보류 [%s]", stk_cd)
                continue
            engine.execute_sell(trade_date, stk_cd, qty, price)
            logger.info("청산 집행 [%s] %d주 @ %d", stk_cd, qty, price)
        except Exception as e:
            logger.error("청산 실패 [%s]: %s", stk_cd, e)

    logger.info("종가베팅 청산 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
