"""체결 동기화 + 체결가 매수 알림 워커 (거래소별, 매수 체결 직후).

매수 워커(signal_executor)는 종가 무렵 시장가/최유리IOC 로 주문만 전송하고,
실제 체결가는 KRX 종가 단일가(15:30) / NXT 종가(19:50 IOC) 이후에야 확정된다.
이 워커가 체결 직후 돌며:
  1) sync_fills 로 live 체결(ka10076)을 fill·position 에 반영하고
  2) 당일 해당 거래소 매수를 **실체결가**로 관리자에게 텔레그램 전송한다.

  --venue krx (15:31)  → KRX 종가 단일가 체결 반영·알림 (NXT 불가 종목)
  --venue nxt (19:55)  → NXT 종가 IOC 체결 반영·알림 (NXT 가능 종목)

paper 는 sync_fills 가 no-op(execute_buy 에서 즉시 시뮬)이라 체결 반영은 건너뛰고
알림만 전송한다. 실행 시간대 가드로 pm2 즉시실행 오발동을 막는다.
"""
import sys
import argparse
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.notifications import notify_admin
from core.repository import order as order_repo
from core.repository import trade_signal as signal_repo

setup_logging()
logger = logging.getLogger("FillsSync")

# (venue → 실행 시각(시), 거래소). signal_executor 의 매수 직후 시각에 맞춘다.
VENUES = {
    "krx": {"hour": 15, "exchange": "KRX"},  # 15:31 — KRX 종가 단일가 체결 후
    "nxt": {"hour": 19, "exchange": "NXT"},  # 19:55 — NXT 종가 IOC 체결 후
}


def _notify_filled_buys(venue: str, dash: str, buys: list[dict], name_map: dict) -> None:
    """당일 해당 거래소 매수를 실체결가로 관리자에게 전송 (전송 실패는 무시)."""
    if not buys:
        return
    try:
        def line(o: dict) -> str:
            nm = name_map.get(o["stk_cd"]) or o["stk_cd"]
            fq = int(o["filled_qty"] or 0)
            if fq < 1 or not o["fill_price"]:
                return f"• {nm}(`{o['stk_cd']}`) {o['qty']}주 — 미체결"
            px = int(o["fill_price"])
            return f"• {nm}(`{o['stk_cd']}`) {fq}주 @{px:,} = {fq * px:,}원"

        filled = [o for o in buys if int(o["filled_qty"] or 0) >= 1 and o["fill_price"]]
        total = sum(int(o["filled_qty"]) * int(o["fill_price"]) for o in filled)
        lines = "\n".join(line(o) for o in buys)
        msg = (
            f"🛒 *[{venue}] 매수 체결* {dash}\n"
            f"{len(filled)}종목 체결 / 매수액 {total:,}원\n"
            f"──────────────────\n{lines}"
        )
        notify_admin(msg)
    except Exception as e:
        logger.error("매수 체결 알림 실패: %s", e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", choices=["krx", "nxt"], required=True)
    args = parser.parse_args()
    cfg = VENUES[args.venue]

    now = datetime.now()
    if now.weekday() >= 5 or now.hour != cfg["hour"]:
        logger.info("[%s] 실행 윈도우(평일 %02d시대)가 아님 — 스킵 (현재 %s)",
                    args.venue.upper(), cfg["hour"], now.strftime("%a %H:%M"))
        return 0

    dash = now.strftime("%Y-%m-%d")
    logger.info("체결 동기화 시작 [%s] (거래일 %s)", args.venue.upper(), dash)

    engine = ExecutionEngine()

    # 1) live 체결을 fill·position 에 반영 (paper 는 no-op)
    synced = sync_fills(engine.client)
    logger.info("체결 반영 %d건", synced)

    # 2) 당일 이 거래소 매수만 추려 실체결가로 알림
    #    venue 판정은 NXT 상장 여부(signal_executor 와 동일): krx=불가, nxt=가능.
    want_nxt = args.venue == "nxt"
    buys = [
        o for o in order_repo.list_by_date(dash)
        if o["side"] == "buy" and o["status"] not in ("rejected", "canceled")
        and engine.data.is_nxt_enabled(o["stk_cd"]) == want_nxt
    ]
    _notify_filled_buys(args.venue.upper(), dash, buys, signal_repo.get_name_map())

    logger.info("체결 동기화 종료 [%s]", args.venue.upper())
    return 0


if __name__ == "__main__":
    sys.exit(main())
