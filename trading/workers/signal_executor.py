"""종가베팅 매수 집행 워커.

PM2 cron 으로 집행 윈도우(평일 16:00, NXT)에 실행:
  pending trade_signal 조회 → ExecutionEngine.execute_buy() → 상태 전이.
멱등성 키로 cron 재실행 시 중복 주문이 발생하지 않는다.
실행 시간대 가드로 오실행(잘못된 시각 실행·pm2 start 즉시실행)을 막는다.
"""
import sys
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.repository import trade_signal as signal_repo
from core.repository import blocklist as blocklist_repo

setup_logging()
logger = logging.getLogger("SignalExecutor")

# 매수 실행 시각(시). ecosystem.config.js 의 cron(0 16 * * 1-5)과 일치시킬 것.
BUY_HOUR = 16


def main() -> int:
    now = datetime.now()
    # 실행 윈도우 가드: 평일 + 지정 시각(시)에만 동작. 그 외(오실행)는 스킵.
    if now.weekday() >= 5 or now.hour != BUY_HOUR:
        logger.info("매수 실행 윈도우(평일 %02d시)가 아님 — 스킵 (현재 %s)",
                    BUY_HOUR, now.strftime("%a %H:%M"))
        return 0

    trade_date = now.strftime("%Y%m%d")
    logger.info("종가베팅 집행 시작 (거래일 %s)", trade_date)

    signals = signal_repo.get_pending_signals(trade_date)
    if not signals:
        logger.info("집행 대기 시그널 없음 — 종료")
        return 0

    block = blocklist_repo.get_codes()
    engine = ExecutionEngine()
    for sig in signals:
        # 매수 제외 종목(blocklist) — 자동매매 이전 보유 등
        if sig["stk_cd"] in block:
            logger.info("blocklist 제외 — signal %s [%s]", sig["id"], sig["stk_cd"])
            signal_repo.update_status(sig["id"], "skipped", note="blocklist")
            continue
        try:
            signal_repo.update_status(sig["id"], "executing")
            resp = engine.execute_buy(trade_date, sig, dmst_stex_tp="NXT")  # 16:00 = NXT 시간대
            # resp 있으면 전송 성공(done), None 이면 차단/수량0/멱등 스킵(skipped)
            signal_repo.update_status(sig["id"], "done" if resp else "skipped")
        except Exception as e:
            logger.error("시그널 %s 집행 실패: %s", sig["id"], e)
            signal_repo.update_status(sig["id"], "rejected", note=str(e))

    logger.info("종가베팅 집행 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
