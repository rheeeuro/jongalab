"""live 체결 동기화 — 키움 체결내역(ka10076)을 우리 주문번호에 매칭해
fill 기록·포지션을 갱신한다.

paper 는 execute_buy/sell 에서 즉시 체결을 시뮬하므로 이 모듈은 no-op.
live 는 주문 전송 후 'sent' 상태로 남고, 이 동기화가 실제 체결을 반영한다.

핵심:
  - 우리 주문(kiwoom_ord_no)에 매칭되는 체결만 반영 → 기존 수동 보유분과 섞이지 않음
  - fill 누적수량 vs 키움 체결수량 차이(delta)만 반영 → 부분체결·반복실행에 멱등
  - 전량 체결(oso_qty=0)이면 주문을 'filled' 로 마감
"""
import logging
from datetime import datetime

from core.kiwoom_data_client import to_int
from core.repository import order as order_repo
from core.repository import fill as fill_repo
from core.repository import position as position_repo
from core.repository import risk_state as risk_repo
from core.repository import audit_log

logger = logging.getLogger("FillSync")


def sync_fills(client) -> int:
    """미반영 live 주문의 체결을 키움에서 가져와 반영. 반영한 주문 수 반환."""
    if getattr(client, "paper", True):
        return 0  # paper 는 즉시 시뮬되므로 동기화 불필요

    pending = order_repo.get_open_sent()
    if not pending:
        return 0

    try:
        resp = client.get_executions(qry_tp="0", sell_tp="0", stex_tp="0")
    except Exception as e:
        logger.error("체결 조회(ka10076) 실패: %s", e)
        return 0

    # ord_no → 누적 체결수량·금액·미체결수량
    agg: dict[str, dict] = {}
    for c in resp.get("cntr", []) or []:
        ono = c.get("ord_no")
        q = to_int(c.get("cntr_qty"))
        if not ono or q <= 0:
            continue
        p = to_int(c.get("cntr_pric"))
        a = agg.setdefault(ono, {"qty": 0, "amt": 0, "oso": 0})
        a["qty"] += q
        a["amt"] += q * p
        a["oso"] = to_int(c.get("oso_qty"))  # 마지막 값(잔여 미체결)

    today = datetime.now().strftime("%Y%m%d")
    applied = 0
    for o in pending:
        info = agg.get(o["kiwoom_ord_no"])
        if not info or info["qty"] <= 0:
            continue
        already = fill_repo.filled_qty(o["id"])
        delta = info["qty"] - already
        if delta > 0:
            price = round(info["amt"] / info["qty"]) if info["qty"] else 0
            fill_repo.record_fill(o["id"], o["stk_cd"], delta, price)
            if o["side"] == "buy":
                position_repo.apply_buy_fill(o["stk_cd"], delta, price)
                audit_log.append("buy_filled_live", o["stk_cd"],
                                 {"order_id": o["id"], "qty": delta, "price": price})
            else:
                realized = position_repo.apply_sell_fill(o["stk_cd"], delta, price)
                risk_repo.add_realized_pnl(today, realized)
                audit_log.append("sell_filled_live", o["stk_cd"],
                                 {"order_id": o["id"], "qty": delta, "price": price, "realized": realized})
            applied += 1
            logger.info("체결 반영 [%s] %s %d주 @%d", o["stk_cd"], o["side"], delta, price)
        if info["oso"] == 0:
            order_repo.mark_sent(o["id"], o["kiwoom_ord_no"], "filled")
    return applied
