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
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.repository import order as order_repo
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo
from core.repository import trade_signal as signal_repo
from core.notifications import notify_admin

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
                                    dmst_stex_tp="NXT", tag="nxt")  # NXT → 최유리IOC
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
    """KRX 09:05 — 잔량 처리(갭상승 전량 / 갭하락 회복 실패 시 전량).

    청산 완료 후, 당일 NXT(08:05)+KRX(09:05) 매도를 합산한 최종 현황을 관리자에게 텔레그램 전송한다.
    """
    plans = plan_repo.get_active_plans()
    if not plans:
        logger.info("[KRX] 활성 청산계획 없음 — plan 없는 잔여 포지션만 정리")
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
                                    dmst_stex_tp="KRX", tag="krx")
                plan_repo.deactivate(plan["trade_date"], stk_cd, "갭상승 KRX 전량매도")
                logger.info("[KRX] %s 갭상승 전량매도 %d주 @%d", stk_cd, pos["qty"], cur)
            else:  # 갭하락
                if cur < plan["nxt_open"]:  # 시초가 회복 못함
                    engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                        dmst_stex_tp="KRX", tag="krx")
                    plan_repo.deactivate(plan["trade_date"], stk_cd, "갭하락 회복실패 전량매도")
                    logger.info("[KRX] %s 갭하락 회복실패 전량매도 %d주 @%d", stk_cd, pos["qty"], cur)
                else:
                    logger.info("[KRX] %s 갭하락 시초가 회복(%d≥%d) — 보유 유지(모니터 감시)",
                                stk_cd, cur, plan["nxt_open"])
        except Exception as e:
            logger.error("[KRX] 청산 실패 [%s]: %s", stk_cd, e)

    # plan 없는 잔여 포지션(비-NXT + 08:05 NXT 매도 실패/누락분) → KRX 정규장 시장가 전량청산
    for p in position_repo.get_open_positions():
        stk_cd = p["stk_cd"]
        if plan_repo.get_plan(trade_date, stk_cd):
            continue  # plan 있는 NXT 종목은 위에서 처리됨
        try:
            cur = engine.data.get_current_price(stk_cd)
            if cur <= 0:
                logger.warning("[KRX] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            engine.execute_sell(trade_date, stk_cd, p["qty"], cur,
                                dmst_stex_tp="KRX", tag="krxfull")
            logger.info("[KRX] %s 잔여 전량청산 %d주 @%d (KRX 시장가)", stk_cd, p["qty"], cur)
        except Exception as e:
            logger.error("[KRX] 비-NXT 청산 실패 [%s]: %s", stk_cd, e)

    # 관리자 텔레그램 청산 현황 전송 (당일 NXT+KRX 합산)
    _notify_sells(trade_date)


def _notify_sells(trade_date: str) -> None:
    """당일 청산 현황을 관리자에게 텔레그램 전송 (paper/live 무관, 전송 실패는 무시).

    KRX 단계만이 아니라 NXT(08:05 절반)+KRX(09:05 잔량) 단계를 종목별로 합산해 '최종' 현황을 보고한다.
    live 는 시장가/IOC 라 실체결가가 사후(fill_sync) 반영되므로, 여기 매도가·손익은
    주문 시점 참조가(가중평균) 기준의 '참조/예상'값임을 명시한다.
    """
    try:
        d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        sells = order_repo.list_sells_by_date(d)
        if not sells:
            return
        names = signal_repo.get_name_map()
        # 종목별 합산: 총수량·매도금액(Σ qty*참조가). 같은 종목의 NXT+KRX 단계 주문을 합친다.
        agg: dict[str, dict] = {}
        for s in sells:
            a = agg.setdefault(s["stk_cd"], {"qty": 0, "amount": 0})
            a["qty"] += s["qty"]
            a["amount"] += s["qty"] * s["price"]
        lines, total, est_pnl = [], 0, 0
        for cd, a in agg.items():
            qty, amount = a["qty"], a["amount"]
            vwap = round(amount / qty) if qty else 0  # 단계 가중평균 매도가
            avg = (position_repo.get_position(cd) or {}).get("avg_price", 0) or 0
            pnl = (vwap - avg) * qty
            total += amount
            est_pnl += pnl
            lines.append(
                f"• {names.get(cd, cd)}(`{cd}`) {qty}주 @{vwap:,} "
                f"(평단 {avg:,} · 예상 {pnl:+,}원)"
            )
        msg = (
            f"💰 *청산 현황 (NXT+KRX 합산)* {d}\n"
            f"{len(agg)}종목 전량매도 / 매도액 {total:,}원\n"
            f"예상 실현손익 {est_pnl:+,}원\n"
            f"──────────────────\n" + "\n".join(lines) + "\n"
            f"_매도가·손익은 주문 시점 참조값(실체결 사후 반영)_"
        )
        notify_admin(msg)
    except Exception as e:
        logger.error("청산현황 알림 실패: %s", e)


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
