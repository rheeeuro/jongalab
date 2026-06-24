"""시초가 청산 윈도우 스탑/저가이탈 + 하드 손절 감시 워커 (30초 폴링).

30초마다 모든 보유 포지션을 점검:
  1) 하드 손절(칼손절): 현재가가 평단(avg_price) 대비 HARD_STOP_LOSS_PCT% 아래면
     settle_plan 유무와 무관하게 **즉시 전량 매도**. 08:01~settle(:05) 사이
     갭하락으로 손실이 커지기 전에 끊는 안전망.
  2) 스탑/저가이탈: settle(NXT 08:05)가 기록한 활성 청산계획(settle_plan)의 stop_price
     이하로 내려가면 **즉시 잔량 전량 매도**.

가동 구간은 평일 08:01~09:30 (NXT 개장 직후 ~ KRX 잔량청산 + 여유)으로 한정한다.
08:00 정각은 NXT 시초 호가가 얇아 한 틱 스파이크로 칼손절이 오발동하기 쉬워 08:01 부터
감시한다(settle 08:05 이전 구간도 하드 손절로 보호). KRX 청산(settle 09:05)이 갭 방향
무관하게 모든 잔량을 정리하므로 그 이후엔 stop_price 감시할 plan 이 없다.

pm2 cron 워커(autorestart:false, cron_restart '1 8 * * 1-5'): 08:01 에 기동돼 가동 구간이
끝나면 스스로 종료하고, 다음 평일 아침 cron 으로 재기동된다. 키움 스톱주문 대신 폴링으로 근사한다.
"""
import time
import logging
from datetime import datetime

from core.config import HARD_STOP_LOSS_PCT
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
    """모니터 가동 구간: 평일 08:01~09:30 (NXT 개장 직후 ~ KRX 잔량청산 + 여유).

    08:00 정각은 NXT 시초 호가가 얇아 한 틱 스파이크로 칼손절이 오발동하기 쉬워
    08:01 부터 감시한다."""
    if now.weekday() >= 5:
        return False
    return (8, 1) <= (now.hour, now.minute) <= (9, 30)


def sell_venue(now: datetime) -> str:
    """매도 거래소: KRX 정규장(09:00~15:30)이면 KRX(시장가), 그 외 NXT 시간대면 NXT(최유리IOC)."""
    hm = (now.hour, now.minute)
    return "KRX" if (9, 0) <= hm < (15, 30) else "NXT"


def check_once(engine: ExecutionEngine) -> None:
    # live 체결을 먼저 반영해 포지션을 최신화 (paper 는 no-op)
    sync_fills(engine.client)
    # 전일 잔여 미체결 자동 취소(개장 중) — 묶임 방지
    cancel_stale_orders(engine.client)

    plans = {p["stk_cd"]: p for p in plan_repo.get_active_plans()}
    positions = {p["stk_cd"]: p for p in position_repo.get_open_positions()}

    # plan 은 있는데 포지션이 사라진 경우 정리
    for stk_cd, plan in plans.items():
        if stk_cd not in positions:
            plan_repo.deactivate(plan["trade_date"], stk_cd, "이미 청산됨")

    # 보유 포지션마다 현재가 1회 조회 → 하드 손절(평단 대비) → 스탑선(settle_plan) 순으로 점검
    for stk_cd, pos in positions.items():
        if pos["qty"] < 1:
            continue
        plan = plans.get(stk_cd)
        trade_date = plan["trade_date"] if plan else datetime.now().strftime("%Y%m%d")
        try:
            cur = engine.data.get_current_price(stk_cd)
            if cur <= 0:
                continue
            # 1) 하드 손절(칼손절): 평단 대비 -HARD_STOP_LOSS_PCT% 이하면 plan 유무 무관 전량매도
            hard_stop = round(pos["avg_price"] * (1 - HARD_STOP_LOSS_PCT / 100))
            if cur <= hard_stop:
                engine.execute_sell(trade_date, stk_cd, pos["qty"], cur,
                                    dmst_stex_tp=sell_venue(datetime.now()), tag="hardstop")
                if plan:
                    plan_repo.deactivate(plan["trade_date"], stk_cd,
                                         f"하드손절 즉시매도 @{cur}(<= {hard_stop}, 평단 {pos['avg_price']})")
                logger.info("하드손절 발동 [%s] 전량매도 %d주 @%d (선 %d, 평단 %d, -%.1f%%)",
                            stk_cd, pos["qty"], cur, hard_stop, pos["avg_price"], HARD_STOP_LOSS_PCT)
                continue
            # 2) 스탑/저가이탈: settle_plan 의 stop_price 이하면 잔량 전량매도
            if plan and cur <= plan["stop_price"]:
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
        logger.info("가동 구간(평일 08:00~09:30) 밖 — 종료")
        return 0
    logger.info("하드손절(-%.1f%%)/스탑 모니터 시작 (30초 폴링, 08:01 기동, 09:30 자동 종료)",
                HARD_STOP_LOSS_PCT)
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
