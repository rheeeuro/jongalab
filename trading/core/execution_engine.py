"""
⚠️ 민감 로직 — 집행 엔진 (주문 사이징·집행)
============================================================
trade_signal → (리스크 검사) → 주문 사이징 → 멱등 주문 전송 → 기록.
이 파일은 자금 손실에 직결되므로 가드 훅 민감 파일 등록을 권장한다
(jongalab/core/trading_engine.py 와 동일 취급).

핵심 불변식:
  - 모든 주문 전 RiskEngine.check() 통과
  - idempotency_key 로 중복 전송 차단 (cron 재실행 안전)
  - 의도/전송/응답을 audit_log 에 append
"""
import logging

from core.kiwoom_order_client import KiwoomOrderClient
from core.kiwoom_data_client import KiwoomDataClient, to_int
from core.risk_engine import RiskEngine
from core.repository import order as order_repo
from core.repository import audit_log
from core.repository import fill as fill_repo
from core.repository import position as position_repo
from core.repository import risk_state as risk_repo

logger = logging.getLogger("ExecutionEngine")


class ExecutionEngine:
    def __init__(
        self,
        client: KiwoomOrderClient | None = None,
        risk: RiskEngine | None = None,
        data: KiwoomDataClient | None = None,
    ):
        self.client = client or KiwoomOrderClient()
        self.risk = risk or RiskEngine()
        self.data = data or KiwoomDataClient()

    @staticmethod
    def idempotency_key(trade_date: str, signal_id: int, side: str) -> str:
        """동일 (거래일, 시그널, 매수/매도) 조합의 중복 주문 방지 키."""
        return f"{trade_date}:{signal_id}:{side}"

    def size_order(self, signal: dict) -> tuple[int, int]:
        """시그널 → (수량, 지정가). 가용현금을 보유 한도 종목수로 균등 배분하고
        종목당 명목 한도로 캡, 현재가로 수량을 산출한다. 살 수 없으면 (0, price).

        budget = min(MAX_NOTIONAL_PER_NAME, 가용현금 // MAX_POSITIONS)
        qty = budget // 현재가
        """
        stk_cd = signal["stk_cd"]
        price = self.data.get_current_price(stk_cd)
        if price <= 0:
            return 0, 0

        avail = to_int(self.client.get_deposit().get("ord_alow_amt"))
        slots = max(1, self.risk.cfg.MAX_POSITIONS)
        budget = min(self.risk.cfg.MAX_NOTIONAL_PER_NAME, avail // slots)
        qty = budget // price
        return qty, price

    def execute_buy(self, trade_date: str, signal: dict) -> dict | None:
        """매수 시그널 1건 집행. 차단/중복이면 None 반환."""
        signal_id = signal["id"]
        stk_cd = signal["stk_cd"]
        key = self.idempotency_key(trade_date, signal_id, "buy")

        # 1. 멱등성 — 이미 전송된 주문이면 스킵
        if order_repo.find_by_idempotency_key(key):
            logger.info("중복 주문 스킵 (idempotency): %s", key)
            return None

        # 2. 사이징 — 살 수량이 안 나오면 스킵
        qty, price = self.size_order(signal)
        if qty < 1:
            audit_log.append("buy_skipped", stk_cd, {"key": key, "reason": "수량 0 (현재가/예수금)", "price": price})
            logger.info("수량 0 스킵 [%s] price=%s", stk_cd, price)
            return None
        notional = qty * price

        # 3. 리스크 검사
        decision = self.risk.check(trade_date, stk_cd, notional)
        if not decision.allowed:
            audit_log.append("buy_blocked", stk_cd, {"key": key, "reason": decision.reason})
            logger.warning("주문 차단 [%s]: %s", stk_cd, decision.reason)
            return None

        # 4. 기록(의도) → 전송 → 결과 반영
        paper = getattr(self.client, "paper", False)
        mode = "paper" if paper else "live"
        order_id = order_repo.create_intended(
            key, signal_id, stk_cd, "buy", qty, price, "limit", mode
        )
        audit_log.append("buy_intended", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        resp = self.client.buy(stk_cd, qty, price, trde_tp="0")  # 0: 보통(지정가)
        audit_log.append("buy_response", stk_cd, {"order_id": order_id, "resp": resp})
        # paper 는 즉시 전량 체결 가정 → 체결·포지션 시뮬레이션. live 는 ka10076 으로 사후 반영.
        order_repo.mark_sent(order_id, resp.get("ord_no"), "filled" if paper else "sent")
        self.risk.record_order(trade_date)  # 일일 주문수 한도 카운팅
        if paper:
            fill_repo.record_fill(order_id, stk_cd, qty, price)
            position_repo.apply_buy_fill(stk_cd, qty, price)
            audit_log.append("buy_filled_paper", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        return resp

    def execute_sell(self, trade_date: str, stk_cd: str, qty: int, price: int) -> dict | None:
        """매도(청산) 집행. 청산은 리스크 게이트를 거치지 않는다(노출 축소·킬스위치 중에도 탈출 허용).
        paper 는 즉시 체결 가정 → 실현손익을 risk_state 에 누적.
        """
        key = self.idempotency_key(trade_date, 0, f"sell:{stk_cd}")
        if order_repo.find_by_idempotency_key(key):
            logger.info("중복 매도 스킵 (idempotency): %s", key)
            return None
        if qty < 1:
            return None

        paper = getattr(self.client, "paper", False)
        mode = "paper" if paper else "live"
        order_id = order_repo.create_intended(key, None, stk_cd, "sell", qty, price, "limit", mode)
        audit_log.append("sell_intended", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        resp = self.client.sell(stk_cd, qty, price, trde_tp="0")
        audit_log.append("sell_response", stk_cd, {"order_id": order_id, "resp": resp})
        order_repo.mark_sent(order_id, resp.get("ord_no"), "filled" if paper else "sent")
        self.risk.record_order(trade_date)
        if paper:
            fill_repo.record_fill(order_id, stk_cd, qty, price)
            realized = position_repo.apply_sell_fill(stk_cd, qty, price)
            risk_repo.add_realized_pnl(trade_date, realized)
            audit_log.append("sell_filled_paper", stk_cd,
                             {"order_id": order_id, "qty": qty, "price": price, "realized": realized})
        return resp
