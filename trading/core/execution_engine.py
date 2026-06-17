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
from core.risk_engine import RiskEngine
from core.repository import order as order_repo
from core.repository import audit_log

logger = logging.getLogger("ExecutionEngine")


class ExecutionEngine:
    def __init__(self, client: KiwoomOrderClient | None = None, risk: RiskEngine | None = None):
        self.client = client or KiwoomOrderClient()
        self.risk = risk or RiskEngine()

    @staticmethod
    def idempotency_key(trade_date: str, signal_id: int, side: str) -> str:
        """동일 (거래일, 시그널, 매수/매도) 조합의 중복 주문 방지 키."""
        return f"{trade_date}:{signal_id}:{side}"

    def size_order(self, signal: dict) -> tuple[int, int]:
        """시그널 → (수량, 지정가). TODO: 예수금·비중 기반 사이징 구현."""
        # 스켈레톤: 사이징 미구현 — 실제 로직은 별도 PR 에서 확정
        raise NotImplementedError("주문 사이징 미구현 (스켈레톤)")

    def execute_buy(self, trade_date: str, signal: dict) -> dict | None:
        """매수 시그널 1건 집행. 차단/중복이면 None 반환."""
        signal_id = signal["id"]
        stk_cd = signal["stk_cd"]
        key = self.idempotency_key(trade_date, signal_id, "buy")

        # 1. 멱등성 — 이미 전송된 주문이면 스킵
        if order_repo.find_by_idempotency_key(key):
            logger.info("중복 주문 스킵 (idempotency): %s", key)
            return None

        # 2. 사이징
        qty, price = self.size_order(signal)
        notional = qty * price

        # 3. 리스크 검사
        decision = self.risk.check(trade_date, stk_cd, notional)
        if not decision.allowed:
            audit_log.append("buy_blocked", stk_cd, {"key": key, "reason": decision.reason})
            logger.warning("주문 차단 [%s]: %s", stk_cd, decision.reason)
            return None

        # 4. 기록(의도) → 전송 → 결과 반영
        order_id = order_repo.create_intended(
            key, signal_id, stk_cd, "buy", qty, price, "limit", "paper"
        )
        audit_log.append("buy_intended", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        resp = self.client.buy(stk_cd, qty, price, trde_tp="0")  # 0: 보통(지정가)
        audit_log.append("buy_response", stk_cd, {"order_id": order_id, "resp": resp})
        order_repo.mark_sent(order_id, resp.get("ord_no"), "sent")
        self.risk.record_order(trade_date)  # 일일 주문수 한도 카운팅
        return resp
