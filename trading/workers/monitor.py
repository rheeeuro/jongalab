"""시초가 청산 윈도우 스탑/저가이탈 감시 워커 (30초 폴링).

settle(NXT 08:05)가 기록한 활성 청산계획(settle_plan)을 30초마다 점검:
  현재가가 스탑/저가이탈선(stop_price) 이하로 내려가면 **즉시 잔량 전량 매도**.

가동 구간은 평일 08:05~09:30 (NXT 절반매도 ~ KRX 잔량청산 + 여유)으로 한정한다.
KRX 청산(settle 09:05)이 갭 방향 무관하게 모든 잔량을 정리하므로 그 이후엔 감시할 plan 이 없다.

pm2 cron 워커(autorestart:false, cron_restart '5 8 * * 1-5'): 08:05 에 기동돼 가동 구간이
끝나면 스스로 종료하고, 다음 평일 아침 cron 으로 재기동된다. 키움 스톱주문 대신 폴링으로 근사한다.
"""
import time
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.order_maintenance import cancel_stale_orders
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo

setup_logging()
logger = logging.getLogger("Monitor")

POLL_SEC = 30


def in_window(now: datetime) -> bool:
    """모니터 가동 구간: 평일 08:05~09:30 (NXT 절반매도 ~ KRX 잔량청산 + 여유)."""
    if now.weekday() >= 5:
        return False
    return (8, 5) <= (now.hour, now.minute) <= (9, 30)


def sell_venue(now: datetime) -> str:
    """매도 거래소: KRX 정규장(09:00~15:30)이면 KRX(시장가), 그 외 NXT 시간대면 NXT(최유리IOC)."""
    hm = (now.hour, now.minute)
    return "KRX" if (9, 0) <= hm < (15, 30) else "NXT"


def check_once(engine: ExecutionEngine) -> None:
    # live 체결을 먼저 반영해 포지션을 최신화 (paper 는 no-op)
    sync_fills(engine.client)
    # 전일 잔여 미체결 자동 취소(개장 중) — 묶임 방지
    cancel_stale_orders(engine.client)
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
                                    dmst_stex_tp=sell_venue(datetime.now()), tag="stop")
                plan_repo.deactivate(plan["trade_date"], stk_cd,
                                     f"스탑/저가이탈 즉시매도 @{cur}(<= {plan['stop_price']})")
                logger.info("스탑 발동 [%s] 전량매도 %d주 @%d (선 %d)",
                            stk_cd, pos["qty"], cur, plan["stop_price"])
        except Exception as e:
            logger.error("모니터 점검 실패 [%s]: %s", stk_cd, e)


def main() -> int:
    if not in_window(datetime.now()):
        logger.info("가동 구간(평일 08:05~09:30) 밖 — 종료")
        return 0
    logger.info("스탑/저가이탈 모니터 시작 (30초 폴링, 09:30 자동 종료)")
    engine = ExecutionEngine()
    while in_window(datetime.now()):
        try:
            check_once(engine)
        except Exception as e:
            logger.error("모니터 루프 오류: %s", e)
        time.sleep(POLL_SEC)
    logger.info("가동 구간 종료 — 모니터 종료")
    return 0


if __name__ == "__main__":
    main()
