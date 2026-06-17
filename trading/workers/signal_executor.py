"""종가베팅 매수 집행 워커 (거래소별 2회).

종목의 NXT 상장 여부(ka10100 nxtEnable)에 따라 각 거래소의 종가 무렵에 매수한다:
  --venue krx (15:20)  → NXT 불가 종목을 KRX 종가단일가에 매수
  --venue nxt (19:50)  → NXT 가능 종목을 NXT 종가 무렵에 매수

배분: 종가랩 시드배분기 로직(점수 가중 비례 + 잔여 그리디 재투입)으로,
해당 거래소 대상 후보 전체에 가용현금(시드)을 한 번에 배분한 뒤 집행한다.
멱등성 키로 중복 방지, 실행 시간대 가드로 오실행 방지, blocklist 제외.
"""
import sys
import argparse
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.seed_allocator import allocate
from core.kiwoom_data_client import to_int
from core.notifications import notify_admin
from core.repository import trade_signal as signal_repo
from core.repository import blocklist as blocklist_repo

setup_logging()
logger = logging.getLogger("SignalExecutor")

# (venue → 실행 시각(시), 거래소). ecosystem.config.js 의 cron 과 일치시킬 것.
VENUES = {
    "krx": {"hour": 15, "exchange": "KRX"},  # 15:20 종가단일가, NXT 불가 종목
    "nxt": {"hour": 19, "exchange": "NXT"},  # 19:50 NXT 종가 무렵, NXT 가능 종목
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", choices=["krx", "nxt"], required=True)
    args = parser.parse_args()
    cfg = VENUES[args.venue]

    now = datetime.now()
    if now.weekday() >= 5 or now.hour != cfg["hour"]:
        logger.info("[%s] 매수 윈도우(평일 %02d시대)가 아님 — 스킵 (현재 %s)",
                    args.venue.upper(), cfg["hour"], now.strftime("%a %H:%M"))
        return 0

    trade_date = now.strftime("%Y%m%d")
    logger.info("매수 집행 시작 [%s] 거래소=%s (거래일 %s)",
                args.venue.upper(), cfg["exchange"], trade_date)

    signals = signal_repo.get_pending_signals(trade_date)
    if not signals:
        logger.info("집행 대기 시그널 없음 — 종료")
        return 0

    block = blocklist_repo.get_codes()
    engine = ExecutionEngine()
    want_nxt = args.venue == "nxt"

    # 1) 전체 pending 후보의 거래소·점수 분류 (blocklist 제외)
    #    다른 거래소 몫의 현금을 예약하려면 전체 점수합이 필요하다.
    classified = []  # (sig, stk, score, is_nxt)
    for sig in signals:
        stk = sig["stk_cd"]
        if stk in block:
            logger.info("blocklist 제외 — signal %s [%s]", sig["id"], stk)
            signal_repo.update_status(sig["id"], "skipped", note="blocklist")
            continue
        classified.append((sig, stk, max(float(sig.get("score") or 0), 0),
                           engine.data.is_nxt_enabled(stk)))
    if not classified:
        logger.info("대상 시그널 없음 — 종료")
        return 0

    total_score = sum(s for _, _, s, _ in classified)
    venue_items = [(sig, stk, score) for (sig, stk, score, isn) in classified if isn == want_nxt]
    if not venue_items:
        logger.info("이 거래소 대상 시그널 없음 — 종료")
        return 0
    venue_score = sum(s for _, _, s in venue_items)

    # 2) 시드 = 가용현금의 점수비례 몫 (다른 거래소 몫은 예약, 해당 시간대에 집행)
    cash = to_int(engine.client.get_deposit().get("ord_alow_amt"))
    seed = int(cash * venue_score / total_score) if total_score > 0 else 0
    logger.info("가용현금 %d × (거래소점수 %.0f / 전체 %.0f) → 시드 %d원, 후보 %d종목",
                cash, venue_score, total_score, seed, len(venue_items))

    cands: list[dict] = [
        {"sig": sig, "stk_cd": stk, "score": score,
         "price": engine.data.get_current_price(stk)}
        for sig, stk, score in venue_items
    ]
    allocate(seed, cands)

    # 3) 배분 수량으로 집행
    bought = []  # 텔레그램 매수현황용
    for c in cands:
        sig, stk = c["sig"], c["stk_cd"]
        if c["shares"] < 1:
            logger.info("배분 0주 스킵 [%s] (점수 %.1f, 현재가 %d)", stk, c["score"], c["price"])
            signal_repo.update_status(sig["id"], "skipped", note="배분 0주")
            continue
        sized = {**sig, "_qty": c["shares"], "_price": c["price"]}
        try:
            signal_repo.update_status(sig["id"], "executing")
            resp = engine.execute_buy(trade_date, sized, dmst_stex_tp=cfg["exchange"])
            signal_repo.update_status(sig["id"], "done" if resp else "skipped")
            if resp:
                bought.append({"nm": sig.get("stk_nm") or stk, "cd": stk,
                               "qty": c["shares"], "price": c["price"]})
        except Exception as e:
            logger.error("시그널 %s 집행 실패: %s", sig["id"], e)
            signal_repo.update_status(sig["id"], "rejected", note=str(e))

    # 4) 관리자 텔레그램 매수 현황 전송
    _notify_buys(args.venue.upper(), trade_date, seed, bought)

    logger.info("매수 집행 종료 [%s]", args.venue.upper())
    return 0


def _notify_buys(venue: str, trade_date: str, seed: int, bought: list[dict]) -> None:
    """매수 현황을 관리자에게 텔레그램 전송 (paper/live 무관, 전송 실패는 무시)."""
    try:
        d = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        if not bought:
            msg = f"🛒 *[{venue}] 매수 현황* {d}\n시드 {seed:,}원 — 매수된 종목 없음"
        else:
            total = sum(b["qty"] * b["price"] for b in bought)
            lines = "\n".join(
                f"• {b['nm']}(`{b['cd']}`) {b['qty']}주 @{b['price']:,} = {b['qty']*b['price']:,}원"
                for b in bought
            )
            msg = (
                f"🛒 *[{venue}] 매수 현황* {d}\n"
                f"시드 {seed:,}원 → {len(bought)}종목 / 매수액 {total:,}원\n"
                f"──────────────────\n{lines}"
            )
        notify_admin(msg)
    except Exception as e:
        logger.error("매수현황 알림 실패: %s", e)


if __name__ == "__main__":
    sys.exit(main())
