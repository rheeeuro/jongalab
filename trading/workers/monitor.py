"""시초가 청산 윈도우 트레일링 스탑 + 하드 손절 감시 워커 (15초 폴링).

15초마다 모든 보유 포지션을 점검:
  1) 하드 손절(칼손절): 현재가가 평단(avg_price) 대비 HARD_STOP_LOSS_PCT% 아래면
     settle_plan 유무와 무관하게 **즉시 전량 매도**. 08:01~settle(:05) 사이
     갭하락으로 손실이 커지기 전에 끊는 안전망.
  2) 스탑/저가이탈: settle(NXT 08:05)가 기록한 활성 청산계획(settle_plan)의 stop_price
     이하로 내려가면 **즉시 잔량 전량 매도**.
  3) 트레일링 스탑(고점 추종): 위 둘 다 미발동(=잔량 보유 지속)이면, stop_price 를
     max(기존, 현재가*(1 - TRAIL_PCT/100)) 로 끌어올린다(단조 증가, 절대 내리지 않음).
     KRX 정규장(09:00~) 상승을 잔량으로 따라가며 고점 대비 TRAIL_PCT% 되돌리면 (2)에 걸려
     상승분을 최대한 확보한 가격에 청산한다.

가동 구간은 평일 08:01~09:30 (NXT 개장 직후 ~ KRX 데드라인 + 여유)으로 한정한다.
08:00 정각은 NXT 시초 호가가 얇아 한 틱 스파이크로 칼손절이 오발동하기 쉬워 08:01 부터
감시한다(settle 08:05 이전 구간도 하드 손절로 보호). settle KRX 단계(09:28)가 데드라인으로
미체결 잔량을 강제 청산하므로, 09:05~09:28 구간은 이 트레일링이 잔량을 들고 가며 관리한다.

pm2 cron 워커(autorestart:false, cron_restart '1 8 * * 1-5'): 08:01 에 기동돼 가동 구간이
끝나면 스스로 종료하고, 다음 평일 아침 cron 으로 재기동된다. 키움 스톱주문 대신 폴링으로 근사한다.
"""
import time
import logging
from datetime import datetime

from core.config import HARD_STOP_LOSS_PCT, TRAIL_PCT
from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.order_maintenance import cancel_stale_orders, reconcile_dead_sent
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo
from core.repository import audit_log

setup_logging()
logger = logging.getLogger("Monitor")

POLL_SEC = 15


def _beat(payload: dict) -> None:
    """폴링 하트비트 — 대시보드 '모니터' 탭이 워커 가동 여부를 판별하는 신호.
    기록 실패가 감시 루프를 막지 않도록 예외를 삼킨다(순수 로깅)."""
    try:
        audit_log.append("monitor_poll", None, payload)
    except Exception as e:
        logger.warning("하트비트 기록 실패: %s", e)


def in_window(now: datetime) -> bool:
    """모니터 가동 구간: 평일 08:00~09:30 (NXT 개장 ~ KRX 잔량청산 + 여유).

    08:00·09:00 개장 직후 1분은 시가 체결 전 stale 가격 오발동 위험이 있어
    in_open_warmup() 으로 평가를 스킵한다(가동 자체는 08:00부터)."""
    if now.weekday() >= 5:
        return False
    return (8, 0) <= (now.hour, now.minute) <= (9, 30)


def sell_venue(now: datetime) -> str:
    """매도 거래소: KRX 정규장(09:00~15:30)이면 KRX(시장가), 그 외 NXT 시간대면 NXT(최유리IOC)."""
    hm = (now.hour, now.minute)
    return "KRX" if (9, 0) <= hm < (15, 30) else "NXT"


def in_open_warmup(now: datetime) -> bool:
    """거래소 개장 직후 1분(NXT 08:00~08:01, KRX 09:00~09:01)은 평가를 스킵한다.

    시가 단일가 체결이 ka10001 `cur_prc`에 반영되기 전이라, 이 구간엔 cur_prc 가
    실시간가가 아니라 기준가(=전일 종가)를 돌려줄 수 있다. 그 stale 값으로 스탑/손절을
    판정하면 실제 시장이 스탑 위에 있어도 오발동해 잔량을 강제 청산한다(반대로 진짜
    갭하락 날엔 갭 바닥에 시장가로 던질 위험). 시가가 체결돼 가격이 안정되는 1분간 대기."""
    hm = (now.hour, now.minute)
    return hm == (8, 0) or hm == (9, 0)


def _exit_confirmed(stk_cd: str) -> bool:
    """매도 후 포지션이 실제로 청산됐는지(체결 확인). paper 는 즉시 반영돼 True,
    live 는 다음 폴링의 sync_fills 가 체결을 반영한 뒤 True 가 된다.

    '전송됨(sent)'만으로 plan 을 해제하면, 최유리IOC 가 접수돼도 0주 체결로 소멸했을 때
    감시가 풀려 포지션이 고아가 된다. 실제 청산이 확인될 때만 감시를 해제하기 위한 게이트."""
    p = position_repo.get_position(stk_cd)
    return not p or p["qty"] < 1


def check_once(engine: ExecutionEngine) -> None:
    # 유지보수(housekeeping)는 각 단계를 격리한다 — 한 단계가 실패해도 아래 하드손절/스탑
    # 감시(자금 안전의 핵심)는 반드시 돈다. 과거 reconcile_dead_sent 의 멱등키 충돌 예외가
    # check_once 전체를 매 폴링 중단시켜 모든 종목 감시가 멈췄던 회귀를 막는다.
    #  - 체결 동기화: live 체결을 포지션에 반영(paper no-op)
    #  - 잔여 미체결 취소: 전일 잔여 미체결 자동 취소(개장 중 묶임 방지)
    #  - 죽은 주문 정리: 0주 체결로 소멸한 'sent' 주문 정리 + 멱등키 해제(같은 tag 재매도 허용)
    for label, step in (("체결 동기화", sync_fills),
                        ("잔여 미체결 취소", cancel_stale_orders),
                        ("죽은 주문 정리", reconcile_dead_sent)):
        try:
            step(engine.client)
        except Exception as e:
            logger.error("%s 실패(감시는 계속 진행): %s", label, e)

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
            cur = engine.data.get_market_price(stk_cd)
            if cur <= 0:
                continue
            # 1) 하드 손절(칼손절): 평단 대비 -HARD_STOP_LOSS_PCT% 이하면 plan 유무 무관 전량매도
            hard_stop = round(pos["avg_price"] * (1 - HARD_STOP_LOSS_PCT / 100))
            if cur <= hard_stop:
                sold = engine.execute_sell(trade_date, stk_cd, pos["qty"], cur,
                                           dmst_stex_tp=sell_venue(datetime.now()), tag="hardstop")
                audit_log.append("monitor_hardstop", stk_cd, {
                    "cur": cur, "hard_stop": hard_stop, "avg_price": pos["avg_price"],
                    "qty": pos["qty"], "pct": HARD_STOP_LOSS_PCT, "sent": bool(sold)})
                if sold and _exit_confirmed(stk_cd):
                    if plan:
                        plan_repo.deactivate(plan["trade_date"], stk_cd,
                                             f"하드손절 청산완료 @{cur}(<= {hard_stop}, 평단 {pos['avg_price']})")
                    logger.info("하드손절 청산완료 [%s] %d주 @%d (선 %d, 평단 %d, -%.1f%%)",
                                stk_cd, pos["qty"], cur, hard_stop, pos["avg_price"], HARD_STOP_LOSS_PCT)
                elif sold:
                    logger.info("하드손절 매도 전송 [%s] @%d — 체결 미확인, 다음 폴링에서 재확인/재시도",
                                stk_cd, cur)
                else:
                    logger.warning("하드손절 매도 거부/미전송 [%s] @%d (선 %d) — plan 유지, 다음 폴링 재시도",
                                   stk_cd, cur, hard_stop)
                continue
            # 2) 스탑/저가이탈: settle_plan 의 stop_price 이하면 잔량 전량매도
            if plan and cur <= plan["stop_price"]:
                sold = engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                           dmst_stex_tp=sell_venue(datetime.now()), tag="stop")
                audit_log.append("monitor_stop", stk_cd, {
                    "cur": cur, "stop": plan["stop_price"], "qty": pos["qty"], "sent": bool(sold)})
                if sold and _exit_confirmed(stk_cd):
                    plan_repo.deactivate(plan["trade_date"], stk_cd,
                                         f"스탑/저가이탈 청산완료 @{cur}(<= {plan['stop_price']})")
                    logger.info("스탑 청산완료 [%s] %d주 @%d (선 %d)",
                                stk_cd, pos["qty"], cur, plan["stop_price"])
                elif sold:
                    logger.info("스탑 매도 전송 [%s] @%d — 체결 미확인, plan 유지(다음 폴링 재확인/재시도)",
                                stk_cd, cur)
                else:
                    logger.warning("스탑 매도 거부/미전송 [%s] @%d (선 %d) — plan 유지, 다음 폴링 재시도",
                                   stk_cd, cur, plan["stop_price"])
            # 3) 트레일링 스탑: 매도 미발동(잔량 보유 지속) 시 고점 추종으로 스탑선 상향.
            #    cur > stop_price 가 보장되는 분기라 같은 틱 재발동 없음(새 스탑 = cur*(1-pct) < cur).
            elif plan:
                trail_stop = round(cur * (1 - TRAIL_PCT / 100))
                if trail_stop > plan["stop_price"] and plan_repo.raise_stop(
                        plan["trade_date"], stk_cd, trail_stop, note=f"trail @{cur}"):
                    logger.info("트레일링 [%s] 스탑 상향 %d→%d (현재가 %d, -%.1f%%)",
                                stk_cd, plan["stop_price"], trail_stop, cur, TRAIL_PCT)
                    audit_log.append("monitor_trail", stk_cd, {
                        "old": plan["stop_price"], "new": trail_stop, "cur": cur, "pct": TRAIL_PCT})
        except Exception as e:
            logger.error("모니터 점검 실패 [%s]: %s", stk_cd, e)


def main() -> int:
    if not in_window(datetime.now()):
        logger.info("가동 구간(평일 08:00~09:30) 밖 — 종료")
        return 0
    logger.info("하드손절(-%.1f%%)/스탑 모니터 시작 (15초 폴링, 08:00 기동, 08:00·09:00 워밍업 스킵, 09:30 자동 종료)",
                HARD_STOP_LOSS_PCT)
    audit_log.append("monitor_start", None, {
        "poll_sec": POLL_SEC, "hard_stop_pct": HARD_STOP_LOSS_PCT, "trail_pct": TRAIL_PCT})
    engine = ExecutionEngine()
    while in_window(datetime.now()):
        now = datetime.now()
        if in_open_warmup(now):
            logger.info("개장 워밍업 %02d:%02d — 시가 체결 전 stale 가격 오발동 방지 위해 평가 스킵",
                        now.hour, now.minute)
            _beat({"warmup": True})
            time.sleep(POLL_SEC)
            continue
        try:
            check_once(engine)
            _beat({"positions": len(position_repo.get_open_positions())})
        except Exception as e:
            logger.error("모니터 루프 오류: %s", e)
        time.sleep(POLL_SEC)
    logger.info("가동 구간 종료 — 모니터 종료")
    audit_log.mark_worker_done("monitor")  # watchdog 완료 마커(미실행 감시)
    return 0


if __name__ == "__main__":
    main()
