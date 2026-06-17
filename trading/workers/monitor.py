"""장중 스탑/저가이탈 감시 워커 (1분 폴링, 상시 실행).

settle(NXT 08:05)가 기록한 활성 청산계획(settle_plan)을 1분마다 점검:
  현재가가 스탑/저가이탈선(stop_price) 이하로 내려가면 **즉시 잔량 전량 매도**.
세션 시간(평일 08:00~20:00, NXT 운영시간) 밖에서는 쉰다.

pm2 상시 워커(autorestart). 키움 스톱주문 대신 폴링으로 '즉시 매도'를 근사한다.
"""
import time
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo

setup_logging()
logger = logging.getLogger("Monitor")

POLL_SEC = 60


def in_session(now: datetime) -> bool:
    """평일 08:00~20:00 (NXT 운영시간)."""
    return now.weekday() < 5 and 8 <= now.hour < 20


def check_once(engine: ExecutionEngine) -> None:
    # live 체결을 먼저 반영해 포지션을 최신화한 뒤 스탑 검사 (paper 는 no-op)
    sync_fills(engine.client)
    for plan in plan_repo.get_active_plans():
        stk_cd = plan["stk_cd"]
        pos = position_repo.get_position(stk_cd)
        if not pos or pos["qty"] < 1:
            plan_repo.deactivate(plan["trade_date"], stk_cd, "이미 청산됨")
            continue
        try:
            cur = engine.data.get_current_price(stk_cd)
            if cur <= 0:
                continue
            if cur <= plan["stop_price"]:
                engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                    dmst_stex_tp="SOR", tag="stop")
                plan_repo.deactivate(plan["trade_date"], stk_cd,
                                     f"스탑/저가이탈 즉시매도 @{cur}(<= {plan['stop_price']})")
                logger.info("스탑 발동 [%s] 전량매도 %d주 @%d (선 %d)",
                            stk_cd, pos["qty"], cur, plan["stop_price"])
        except Exception as e:
            logger.error("모니터 점검 실패 [%s]: %s", stk_cd, e)


def main() -> int:
    logger.info("스탑/저가이탈 모니터 시작 (1분 폴링)")
    engine = ExecutionEngine()
    while True:
        now = datetime.now()
        if in_session(now):
            try:
                check_once(engine)
            except Exception as e:
                logger.error("모니터 루프 오류: %s", e)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
