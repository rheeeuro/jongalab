"""종가베팅 매수 집행 워커.

PM2 cron 으로 집행 윈도우(평일 14:30~15:00)에 실행:
  pending trade_signal 조회 → ExecutionEngine.execute_buy() → 상태 전이.
멱등성 키로 cron 재실행 시 중복 주문이 발생하지 않는다.
"""
import sys
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.repository import trade_signal as signal_repo

setup_logging()
logger = logging.getLogger("SignalExecutor")


def main() -> int:
    trade_date = datetime.now().strftime("%Y%m%d")
    logger.info("종가베팅 집행 시작 (거래일 %s)", trade_date)

    signals = signal_repo.get_pending_signals(trade_date)
    if not signals:
        logger.info("집행 대기 시그널 없음 — 종료")
        return 0

    engine = ExecutionEngine()
    for sig in signals:
        try:
            signal_repo.update_status(sig["id"], "executing")
            resp = engine.execute_buy(trade_date, sig)
            signal_repo.update_status(sig["id"], "done" if resp else "rejected")
        except NotImplementedError:
            logger.warning("집행 로직 미구현(스켈레톤) — signal %s 보류", sig["id"])
            signal_repo.update_status(sig["id"], "pending")
        except Exception as e:
            logger.error("시그널 %s 집행 실패: %s", sig["id"], e)
            signal_repo.update_status(sig["id"], "rejected", note=str(e))

    logger.info("종가베팅 집행 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
