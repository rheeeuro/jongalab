"""시초가 2단계 청산 워커 (NXT 08:05 / KRX 09:05).

전략:
  [NXT 08:05]  NXT 시초가 vs 매수 평단으로 갭 판정 → 절반 매도, 잔량 감시계획(settle_plan) 기록
     - 갭상승: 스탑선 = 시초가(절반 매도가)  → 이탈 시 1분 모니터가 즉시 전량 매도
     - 갭하락: 저가이탈선 = 시초가          → 이탈 시 1분 모니터가 즉시 전량 매도
  [KRX 09:05]  잔량 처리
     - 갭상승: 전량 매도
     - 갭하락: 시초가 회복 못하면(현재가 < 시초가) 전량 매도, 회복 시 보유 유지(모니터 계속 감시)

가정(미세 조정 가능): '시초가'는 각 단계 실행 시점의 현재가로 근사. '저가 이탈선'은 NXT 시초가.
"""
import sys
import argparse
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.config import SELL_EXCHANGE
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo

setup_logging()
logger = logging.getLogger("Settle")


def run_nxt(engine: ExecutionEngine, trade_date: str) -> None:
    """NXT 08:05 — 갭 판정 + 절반 매도 + 감시계획 기록."""
    positions = position_repo.get_open_positions()
    if not positions:
        logger.info("[NXT] 보유 포지션 없음 — 종료")
        return
    for p in positions:
        stk_cd, qty, avg = p["stk_cd"], p["qty"], p["avg_price"]
        # 비-NXT 종목은 NXT 단계 대상이 아님(NXT 미상장) → 09:05 KRX 단계에서 청산
        if not engine.data.is_nxt_enabled(stk_cd):
            logger.info("[NXT] %s 비-NXT — 08:05 단계 건너뜀(09:05 KRX 청산)", stk_cd)
            continue
        try:
            nxt_open = engine.data.get_current_price(stk_cd)
            if nxt_open <= 0:
                logger.warning("[NXT] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            gap_dir = "up" if nxt_open > avg else "down"
            half = (qty + 1) // 2  # 올림(소숫점 올림) — 1주는 전량(=1)
            if half >= 1:
                engine.execute_sell(trade_date, stk_cd, half, nxt_open,
                                    dmst_stex_tp=SELL_EXCHANGE, tag="nxt")
            remaining = qty - half
            if remaining > 0:
                # 잔량 감시계획: 스탑/저가이탈선 = 시초가
                plan_repo.upsert_plan(trade_date, stk_cd, gap_dir, avg, nxt_open,
                                      stop_price=nxt_open, note=f"nxt half={half}")
                logger.info("[NXT] %s 갭%s 절반매도 %d주 @%d (잔량 %d, 스탑 %d)",
                            stk_cd, gap_dir, half, nxt_open, remaining, nxt_open)
            else:
                logger.info("[NXT] %s 갭%s 전량매도 %d주 @%d (잔량 0 — 감시계획 없음)",
                            stk_cd, gap_dir, half, nxt_open)
        except Exception as e:
            logger.error("[NXT] 청산 실패 [%s]: %s", stk_cd, e)


def run_krx(engine: ExecutionEngine, trade_date: str) -> None:
    """KRX 09:05 — 잔량 처리(갭상승 전량 / 갭하락 회복 실패 시 전량)."""
    plans = plan_repo.get_active_plans()
    if not plans:
        logger.info("[KRX] 활성 청산계획 없음 — 종료")
        return
    for plan in plans:
        stk_cd = plan["stk_cd"]
        pos = position_repo.get_position(stk_cd)
        if not pos or pos["qty"] < 1:
            plan_repo.deactivate(plan["trade_date"], stk_cd, "이미 청산됨")
            continue
        try:
            cur = engine.data.get_current_price(stk_cd)
            if cur <= 0:
                logger.warning("[KRX] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            if plan["gap_dir"] == "up":
                engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                    dmst_stex_tp=SELL_EXCHANGE, tag="krx")
                plan_repo.deactivate(plan["trade_date"], stk_cd, "갭상승 KRX 전량매도")
                logger.info("[KRX] %s 갭상승 전량매도 %d주 @%d", stk_cd, pos["qty"], cur)
            else:  # 갭하락
                if cur < plan["nxt_open"]:  # 시초가 회복 못함
                    engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                        dmst_stex_tp=SELL_EXCHANGE, tag="krx")
                    plan_repo.deactivate(plan["trade_date"], stk_cd, "갭하락 회복실패 전량매도")
                    logger.info("[KRX] %s 갭하락 회복실패 전량매도 %d주 @%d", stk_cd, pos["qty"], cur)
                else:
                    logger.info("[KRX] %s 갭하락 시초가 회복(%d≥%d) — 보유 유지(모니터 감시)",
                                stk_cd, cur, plan["nxt_open"])
        except Exception as e:
            logger.error("[KRX] 청산 실패 [%s]: %s", stk_cd, e)

    # 비-NXT 포지션(08:05 단계를 건너뜀, plan 없음) → KRX 에서 전량 청산
    for p in position_repo.get_open_positions():
        stk_cd = p["stk_cd"]
        if engine.data.is_nxt_enabled(stk_cd):
            continue  # NXT 종목은 위 plan 로직에서 처리
        if plan_repo.get_plan(trade_date, stk_cd):
            continue  # 이미 plan 있으면 위에서 처리됨
        try:
            cur = engine.data.get_current_price(stk_cd)
            if cur <= 0:
                logger.warning("[KRX] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            engine.execute_sell(trade_date, stk_cd, p["qty"], cur,
                                dmst_stex_tp=SELL_EXCHANGE, tag="krxfull")
            logger.info("[KRX] %s 비-NXT 전량청산 %d주 @%d", stk_cd, p["qty"], cur)
        except Exception as e:
            logger.error("[KRX] 비-NXT 청산 실패 [%s]: %s", stk_cd, e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", choices=["nxt", "krx"], required=True)
    args = parser.parse_args()

    now = datetime.now()
    # 실행 윈도우 가드: 평일 + 지정 시간대에만 동작(오실행·pm2 start 즉시실행 방지).
    expected_hour = 8 if args.venue == "nxt" else 9
    if now.weekday() >= 5 or now.hour != expected_hour:
        logger.info("[%s] 실행 윈도우(%s 평일 %02d시)가 아님 — 스킵",
                    args.venue.upper(), args.venue.upper(), expected_hour)
        return 0

    trade_date = now.strftime("%Y%m%d")
    logger.info("청산 시작 [%s] (거래일 %s)", args.venue.upper(), trade_date)
    engine = ExecutionEngine()
    sync_fills(engine.client)  # 직전 체결을 포지션에 반영 후 청산 판단 (paper 는 no-op)
    if args.venue == "nxt":
        run_nxt(engine, trade_date)
    else:
        run_krx(engine, trade_date)
    logger.info("청산 종료 [%s]", args.venue.upper())
    return 0


if __name__ == "__main__":
    sys.exit(main())
