"""자동매매 실현손익 조회 — trading DB(집행 도메인)를 읽어 주간 매매 성과를 집계.

종가베팅은 'trade_date 종가 매수 → 익일 아침 매도'다. 실현손익(realized)은 매도 체결 시점에
trading.audit_log(sell_filled_*) payload 에 기록된다. 가중치 튜닝은 '그 종목이 매수일에 받았던
종합점수 지표'와 성과를 짝지어야 하므로, 매도의 realized 를 직전 매수일(=trade_date)로 귀속시킨다.

읽기 전용. trading DB 는 core.db.get_trading_db() 로 연결한다(closing_bet 핸드오프와 동일 경로).
"""
import json
import logging
from datetime import date, datetime

from core.db import get_trading_db

logger = logging.getLogger("TradeResult")


def _parse_realized(payload) -> int:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {}
    return int((payload or {}).get("realized") or 0)


def get_weekly_trade_results(week_start: str, week_end: str) -> list[dict]:
    """[week_start, week_end] (YYYY-MM-DD, 매수일 기준) 에 매수된 종목별 실현손익 집계.

    반환: [{trade_date, stk_cd, realized_pnl, buy_price, qty}] (실제 청산이 잡힌 종목만).
    매도는 매수 익일 아침에 발생하므로 매도 이벤트는 week_end+5일까지 조회한 뒤,
    각 매도를 '그 매도일 직전 최신 매수'에 귀속시켜 trade_date 로 환원한다.
    """
    with get_trading_db() as (conn, cursor):
        # 1) 매도 체결 이벤트별 실현손익 (기간 + 익주 초반까지)
        cursor.execute(
            "SELECT stk_cd, payload, created_at FROM audit_log "
            "WHERE event IN ('sell_filled_paper', 'sell_filled_live') "
            "AND created_at >= %s AND created_at < %s + INTERVAL 5 DAY "
            "ORDER BY created_at",
            (week_start, week_end),
        )
        sell_rows = cursor.fetchall()

        # 2) 매수 체결 — 라운드트립 매칭용 (종목별 체결일/평단/수량)
        cursor.execute(
            "SELECT o.stk_cd, o.created_at, "
            "ROUND(SUM(f.qty * f.price) / NULLIF(SUM(f.qty), 0)) AS fill_price, "
            "COALESCE(SUM(f.qty), 0) AS filled_qty "
            "FROM `order` o LEFT JOIN fill f ON f.order_id = o.id "
            "WHERE o.side = 'buy' AND o.status NOT IN ('intended', 'rejected', 'canceled') "
            "AND o.created_at < %s + INTERVAL 5 DAY "
            "GROUP BY o.id ORDER BY o.created_at",
            (week_end,),
        )
        buy_rows = cursor.fetchall()

    # 종목별 매수 체결 시각 목록 (오름차순)
    buys_by_stock: dict[str, list[dict]] = {}
    for b in buy_rows:
        if not b.get("filled_qty"):
            continue
        buys_by_stock.setdefault(b["stk_cd"], []).append(b)

    def _latest_buy_before(stk_cd: str, when: datetime) -> dict | None:
        match = None
        for b in buys_by_stock.get(stk_cd, []):
            if b["created_at"] < when:
                match = b  # 오름차순이라 마지막으로 통과한 게 '직전 최신 매수'
            else:
                break
        return match

    # (stk_cd, trade_date) 단위로 실현손익 누적
    agg: dict[tuple[str, str], dict] = {}
    for s in sell_rows:
        buy = _latest_buy_before(s["stk_cd"], s["created_at"])
        if buy is None:
            continue
        trade_date = buy["created_at"].date().isoformat()
        if not (week_start <= trade_date <= week_end):
            continue
        key = (s["stk_cd"], trade_date)
        entry = agg.setdefault(key, {
            "trade_date": trade_date,
            "stk_cd": s["stk_cd"],
            "realized_pnl": 0,
            "buy_price": int(buy["fill_price"]) if buy["fill_price"] else 0,
            "qty": int(buy["filled_qty"] or 0),
        })
        entry["realized_pnl"] += _parse_realized(s.get("payload"))

    results = sorted(agg.values(), key=lambda r: (r["trade_date"], r["stk_cd"]))
    logger.info(f"주간 매매 실현손익 집계: {len(results)}건 ({week_start}~{week_end})")
    return results
