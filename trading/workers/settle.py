"""시초가 2단계 청산 워커 (NXT 08:05 / KRX 09:28 데드라인).

전략:
  [NXT 08:05]  NXT 시초가 vs 매수 평단으로 갭 판정 → 절반 매도, 잔량 감시계획(settle_plan) 기록
     - 갭상승: 스탑선 = 절반매도 체결가(버퍼 없음) → 이후 모니터가 트레일링으로 끌어올림
     - 갭하락: 저가이탈선 = 시초가 - 버퍼          → 이탈 시 모니터가 즉시 전량 매도
  [08:05~09:28]  모니터(monitor.py)가 30초 폴링으로 잔량을 들고 가며 스탑선을 고점 추종으로
     끌어올린다(트레일링 스탑). KRX 정규장 상승분을 잔량으로 최대한 따라간다.
  [KRX 09:28]  데드라인 — 트레일링에 안 걸리고 남은 잔량을 갭 방향 무관 전량 매도(보유 안 함).
     09:30 모니터 종료 직전, 미체결 잔량을 정리하는 최종 백스톱.

가정(미세 조정 가능): '시초가'는 각 단계 실행 시점의 현재가로 근사. '저가 이탈선'은 NXT 시초가.
"""
import sys
import argparse
import logging
from datetime import datetime

from core.config import STOP_BUFFER_PCT
from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.repository import audit_log
from core.repository import order as order_repo
from core.repository import fill as fill_repo
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo
from core.repository import trade_signal as signal_repo
from core.notifications import notify_admin

setup_logging()
logger = logging.getLogger("Settle")


def _half_sell_fill_price(trade_date: str, stk_cd: str, fallback: int) -> int:
    """NXT 절반매도(tag='nxt')의 실체결 수량가중평균가. 미체결/조회불가면 fallback(시초가).

    live 는 체결이 ka10076 으로 사후 반영되므로 호출 전 sync_fills 필요.
    paper 는 주문 참조가(=시초가)로 즉시 체결돼 fallback 과 동일하게 수렴한다.
    """
    key = ExecutionEngine.idempotency_key(trade_date, 0, f"sell:nxt:{stk_cd}")
    order = order_repo.find_by_idempotency_key(key)
    if not order:
        return fallback
    fills = fill_repo.get_fills_by_order(order["id"])
    tot_qty = sum(int(f["qty"]) for f in fills)
    if tot_qty <= 0:
        return fallback
    amount = sum(int(f["qty"]) * int(f["price"]) for f in fills)
    return round(amount / tot_qty)


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
            nxt_open = engine.data.get_market_price(stk_cd)
            if nxt_open <= 0:
                logger.warning("[NXT] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            gap_dir = "up" if nxt_open > avg else "down"
            half = qty // 2  # 내림(소숫점 내림) — 1주는 절반=0(매도 안 함, 전량 보유로 회복 대기)
            if half >= 1:
                engine.execute_sell(trade_date, stk_cd, half, nxt_open,
                                    dmst_stex_tp="NXT", tag="nxt")  # NXT → 최유리IOC
            remaining = qty - half
            if remaining > 0:
                if gap_dir == "up":
                    # 갭상승: 스탑선 = 절반매도 체결가(버퍼 없음). 잔량이 절반 판 가격 아래로
                    # 내려가면 모니터가 즉시 전량 매도해 확보한 이익선을 지킨다.
                    sync_fills(engine.client)  # 절반매도 체결 반영(live) 후 실체결가 확인
                    stop_price = _half_sell_fill_price(trade_date, stk_cd, fallback=nxt_open)
                else:
                    # 갭하락: 저가이탈선 = 시초가에서 STOP_BUFFER_PCT% 아래(버퍼). 시초가를 그대로
                    # 잡으면 한 틱만 눌려도 잔량이 즉시 털리므로 시초가 회복 대기를 위한 버퍼를 둔다.
                    stop_price = round(nxt_open * (1 - STOP_BUFFER_PCT / 100))
                plan_repo.upsert_plan(trade_date, stk_cd, gap_dir, avg, nxt_open,
                                      stop_price=stop_price, note=f"nxt half={half}")
                logger.info("[NXT] %s 갭%s 절반매도 %d주 @%d (잔량 %d, 스탑 %d)",
                            stk_cd, gap_dir, half, nxt_open, remaining, stop_price)
            else:
                logger.info("[NXT] %s 갭%s 전량매도 %d주 @%d (잔량 0 — 감시계획 없음)",
                            stk_cd, gap_dir, half, nxt_open)
        except Exception as e:
            logger.error("[NXT] 청산 실패 [%s]: %s", stk_cd, e)


def run_krx(engine: ExecutionEngine, trade_date: str) -> None:
    """KRX 09:28 데드라인 — 트레일링에 안 걸린 잔량 전량 매도(갭 방향 무관, 잔량 보유 안 함).

    08:05~09:28 사이 모니터 트레일링 스탑으로 이미 청산된 종목은 active 계획이 해제(또는 qty=0)돼
    여기서 건너뛴다. 데드라인까지 남은 잔량만 정리한다.
    청산 완료 후, 당일 NXT(08:05)+트레일링+KRX(09:28) 매도를 합산한 최종 현황을 관리자에게 전송한다.
    """
    plans = plan_repo.get_active_plans()
    active_codes = {plan["stk_cd"] for plan in plans}  # 아래 첫 루프가 책임지는 종목
    if not plans:
        logger.info("[KRX] 활성 청산계획 없음 — plan 없는 잔여 포지션만 정리")
    for plan in plans:
        stk_cd = plan["stk_cd"]
        pos = position_repo.get_position(stk_cd)
        if not pos or pos["qty"] < 1:
            plan_repo.deactivate(plan["trade_date"], stk_cd, "이미 청산됨")
            continue
        try:
            cur = engine.data.get_market_price(stk_cd)
            if cur <= 0:
                logger.warning("[KRX] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            sold = engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                       dmst_stex_tp="KRX", tag="krx")
            if not sold:
                logger.warning("[KRX] %s 전량매도 거부/미전송 @%d — plan 유지, 다음 단계 재시도", stk_cd, cur)
                continue
            if plan["gap_dir"] == "up":
                plan_repo.deactivate(plan["trade_date"], stk_cd, "갭상승 KRX 전량매도")
                logger.info("[KRX] %s 갭상승 전량매도 %d주 @%d", stk_cd, pos["qty"], cur)
            else:  # 갭하락 — 회복 여부와 무관하게 전량 매도(잔량 보유 안 함)
                reason = ("갭하락 시초가회복 전량매도" if cur >= plan["nxt_open"]
                          else "갭하락 회복실패 전량매도")
                plan_repo.deactivate(plan["trade_date"], stk_cd, reason)
                logger.info("[KRX] %s %s %d주 @%d", stk_cd, reason, pos["qty"], cur)
        except Exception as e:
            logger.error("[KRX] 청산 실패 [%s]: %s", stk_cd, e)

    # 활성 plan 없는 잔여 포지션 → KRX 정규장 시장가 전량청산 (진짜 데드라인 백스톱).
    #   대상: 비-NXT 종목 + 08:05 NXT 매도 실패/누락분 + "전송됐으나 미체결로 plan 만 비활성화"된 잔량.
    #   (비활성 plan 행도 get_plan 으론 잡히므로, 존재여부가 아닌 active 여부로 판정해야 '보유 안 함'이 보장된다.)
    for p in position_repo.get_open_positions():
        stk_cd = p["stk_cd"]
        if stk_cd in active_codes:
            continue  # 활성 plan 종목은 위 루프에서 처리(또는 거부 시 재시도 대기)
        try:
            cur = engine.data.get_market_price(stk_cd)
            if cur <= 0:
                logger.warning("[KRX] 현재가 조회 실패 — 보류 [%s]", stk_cd)
                continue
            engine.execute_sell(trade_date, stk_cd, p["qty"], cur,
                                dmst_stex_tp="KRX", tag="krxfull")
            logger.info("[KRX] %s 잔여 전량청산 %d주 @%d (KRX 시장가)", stk_cd, p["qty"], cur)
        except Exception as e:
            logger.error("[KRX] 비-NXT 청산 실패 [%s]: %s", stk_cd, e)

    # 관리자 텔레그램 청산 현황 전송 (당일 NXT+KRX 합산)
    _notify_sells(engine, trade_date)


def _notify_sells(engine: ExecutionEngine, trade_date: str) -> None:
    """당일 청산 현황을 관리자에게 텔레그램 전송 (paper/live 무관, 전송 실패는 무시).

    대시보드와 **같은 권위값**으로 보고한다: 실체결가(fill_price)·체결수량으로 집계하고,
    실현손익은 audit_log(체결 기반) 권위값을 쓴다. 참조가/주문수량 추정이 부호까지 뒤집을 만큼
    실제와 괴리됐던 문제를 막기 위함. 전송 직전 체결을 한 번 더 동기화한다(live; paper no-op).
    NXT(08:05 절반)+트레일링+KRX(09:28 잔량) 단계를 종목별로 합산해 '최종' 현황을 보고한다.
    """
    try:
        sync_fills(engine.client)  # 최신 체결 반영 후 집계 (참조가/미체결 괴리 최소화)
        d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        sells = [o for o in order_repo.list_by_date(d) if o["side"] == "sell"
                 and o["status"] not in ("intended", "rejected", "canceled")]
        if not sells:
            return
        names = signal_repo.get_name_map()
        realized_map = audit_log.realized_by_date(d)  # 종목별 실현손익(권위값)
        # 종목별 합산: 체결수량·체결금액(Σ 체결수량*체결가). 미체결분만 참조가/주문수량으로 폴백.
        agg: dict[str, dict] = {}
        pending = False
        for s in sells:
            qty = int(s["filled_qty"] or 0)
            px = s["fill_price"]
            if qty <= 0 or px is None:  # 아직 체결 미반영 → 참조가/주문수량 폴백
                qty, px, pending = s["qty"], s["price"], True
            a = agg.setdefault(s["stk_cd"], {"qty": 0, "amount": 0})
            a["qty"] += qty
            a["amount"] += qty * px
        lines, total, pnl_total = [], 0, 0
        for cd, a in agg.items():
            qty, amount = a["qty"], a["amount"]
            vwap = round(amount / qty) if qty else 0  # 체결 가중평균 매도가
            pnl = realized_map.get(cd, 0)
            total += amount
            pnl_total += pnl
            lines.append(
                f"• {names.get(cd, cd)}(`{cd}`) {qty}주 @{vwap:,} (실현 {pnl:+,}원)"
            )
        note = ("_일부 미체결분은 참조가 기준 — 체결 후 정정_" if pending
                else "_실체결가·실현손익(audit) 기준_")
        msg = (
            f"💰 *청산 현황 (NXT+KRX 합산)* {d}\n"
            f"{len(agg)}종목 전량매도 / 매도액 {total:,}원\n"
            f"실현손익 {pnl_total:+,}원\n"
            f"──────────────────\n" + "\n".join(lines) + "\n"
            f"{note}"
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
