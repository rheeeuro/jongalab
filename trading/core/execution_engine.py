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

    @staticmethod
    def _now_trde_tp(dmst_stex_tp: str) -> str:
        """거래소별 '즉시 체결' 주문타입.
        KRX 는 시장가(3)를 받지만 NXT 는 시장가 미지원 → 최유리지정가 IOC(16)로 즉시 체결.
        (SOR/기타는 KRX 라우팅 가정으로 시장가(3))
        """
        return "16" if dmst_stex_tp == "NXT" else "3"

    def size_order(self, signal: dict) -> tuple[int, int]:
        """시그널 → (수량, 지정가).

        기본: 매수 워커(signal_executor)가 시드배분기(core.seed_allocator)로 후보 전체에
        배분한 수량을 signal['_qty']/['_price'] 로 주입한다 → 그대로 사용.
        (fallback) 사전 배분이 없으면 단일 종목 사이징(가용현금 // MAX_POSITIONS, 종목당 캡).
        """
        if signal.get("_qty") is not None:
            return int(signal["_qty"] or 0), int(signal.get("_price") or 0)

        stk_cd = signal["stk_cd"]
        price = self.data.get_current_price(stk_cd)
        if price <= 0:
            return 0, 0
        avail = to_int(self.client.get_deposit().get("ord_alow_amt"))
        slots = max(1, self.risk.cfg.MAX_POSITIONS)
        budget = min(self.risk.cfg.MAX_NOTIONAL_PER_NAME, avail // slots)
        qty = budget // price
        return qty, price

    def execute_buy(self, trade_date: str, signal: dict, dmst_stex_tp: str = "KRX") -> dict | None:
        """매수 시그널 1건 집행. 차단/중복이면 None 반환.
        dmst_stex_tp: 거래소 라우팅 — 16:00 매수는 NXT 시간대라 'NXT'.
        """
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
            key, signal_id, stk_cd, "buy", qty, price, "market", mode
        )
        audit_log.append("buy_intended", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        # 거래소별 즉시체결 주문타입(KRX 시장가 / NXT 최유리IOC). ord_uv 빈값(price=0).
        resp = self.client.buy(stk_cd, qty, 0, trde_tp=self._now_trde_tp(dmst_stex_tp),
                               dmst_stex_tp=dmst_stex_tp)
        audit_log.append("buy_response", stk_cd, {"order_id": order_id, "resp": resp})
        # live 에서 키움이 거부(return_code≠0 또는 주문번호 없음)하면 rejected 로 기록하고 중단
        if not paper and (resp.get("return_code") != 0 or not resp.get("ord_no")):
            order_repo.mark_sent(order_id, None, "rejected")
            audit_log.append("buy_rejected", stk_cd, {"order_id": order_id, "resp": resp})
            logger.warning("매수 거부 [%s]: %s", stk_cd, resp.get("return_msg"))
            return None
        # paper 는 즉시 전량 체결 가정 → 체결·포지션 시뮬레이션. live 는 ka10076 으로 사후 반영.
        order_repo.mark_sent(order_id, resp.get("ord_no"), "filled" if paper else "sent")
        self.risk.record_order(trade_date)  # 일일 주문수 한도 카운팅
        if paper:
            fill_repo.record_fill(order_id, stk_cd, qty, price)
            position_repo.apply_buy_fill(stk_cd, qty, price)
            audit_log.append("buy_filled_paper", stk_cd, {"order_id": order_id, "qty": qty, "price": price})
        return resp

    def execute_sell(self, trade_date: str, stk_cd: str, qty: int, price: int,
                     dmst_stex_tp: str = "KRX", tag: str = "") -> dict | None:
        """매도(청산) 집행. 청산은 리스크 게이트를 거치지 않는다(노출 축소·킬스위치 중에도 탈출 허용).
        paper 는 즉시 체결 가정 → 실현손익을 risk_state 에 누적.
        dmst_stex_tp: 거래소(NXT 08시 매도 / KRX 09시 매도).
        tag: 멱등 키 구분자 — 같은 종목·거래일에 단계별(nxt-half/krx/stop) 매도를 구별한다.
        """
        suffix = f"sell:{tag}:{stk_cd}" if tag else f"sell:{stk_cd}"
        key = self.idempotency_key(trade_date, 0, suffix)
        if order_repo.find_by_idempotency_key(key):
            logger.info("중복 매도 스킵 (idempotency): %s", key)
            return None
        if qty < 1:
            return None

        paper = getattr(self.client, "paper", False)
        mode = "paper" if paper else "live"
        order_id = order_repo.create_intended(key, None, stk_cd, "sell", qty, price, "market", mode)
        audit_log.append("sell_intended", stk_cd, {"order_id": order_id, "qty": qty, "price": price, "tag": tag})
        # 거래소별 즉시체결 주문타입(KRX 시장가 / NXT 최유리IOC). ord_uv 빈값.
        resp = self.client.sell(stk_cd, qty, 0, trde_tp=self._now_trde_tp(dmst_stex_tp),
                                dmst_stex_tp=dmst_stex_tp)
        audit_log.append("sell_response", stk_cd, {"order_id": order_id, "resp": resp})
        # live 에서 키움이 거부하면 rejected 로 기록하고 중단(가짜 매도기록 방지)
        if not paper and (resp.get("return_code") != 0 or not resp.get("ord_no")):
            order_repo.mark_sent(order_id, None, "rejected")
            audit_log.append("sell_rejected", stk_cd, {"order_id": order_id, "resp": resp})
            logger.warning("매도 거부 [%s]: %s", stk_cd, resp.get("return_msg"))
            return None
        order_repo.mark_sent(order_id, resp.get("ord_no"), "filled" if paper else "sent")
        self.risk.record_order(trade_date)
        if paper:
            fill_repo.record_fill(order_id, stk_cd, qty, price)
            realized = position_repo.apply_sell_fill(stk_cd, qty, price)
            risk_repo.add_realized_pnl(trade_date, realized)
            audit_log.append("sell_filled_paper", stk_cd,
                             {"order_id": order_id, "qty": qty, "price": price, "realized": realized})
        return resp
