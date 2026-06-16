"""
⚠️ 민감 로직 — 리스크 엔진 (한도·서킷브레이커·킬스위치 판정)
============================================================
모든 주문은 집행 전 RiskEngine.check() 를 통과해야 한다.
이 파일은 자금 손실에 직결되므로 가드 훅 민감 파일 등록을 권장한다
(jongalab/core/trading_engine.py 와 동일 취급).

[검사 순서]
  1. 킬스위치 (env TRADING_KILL_SWITCH OR DB kill_switch) → 차단
  2. 일일 주문 건수 한도
  3. 종목당 최대 비중
  4. 일일 최대 손실 → 초과 시 킬스위치 자동 ON (서킷브레이커)
"""
import logging
from dataclasses import dataclass

from core.config import TRADING_KILL_SWITCH
from core.repository import risk_state as risk_repo

logger = logging.getLogger("RiskEngine")


class RiskConfig:
    """리스크 한도 파라미터 (추후 DB 주입 가능)."""
    MAX_ORDERS_PER_DAY = 10
    MAX_NOTIONAL_PER_NAME = 5_000_000      # 종목당 최대 명목금액(원)
    MAX_DAILY_LOSS = 3_000_000             # 일일 최대 손실(원) → 초과 시 서킷브레이커
    MAX_POSITIONS = 5


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskEngine:
    def __init__(self, cfg: RiskConfig | None = None):
        self.cfg = cfg or RiskConfig()

    def kill_switch_on(self) -> bool:
        """env 플래그 OR DB 플래그 (둘 중 하나라도 켜지면 정지)."""
        if TRADING_KILL_SWITCH:
            return True
        try:
            return risk_repo.get_kill_switch()
        except Exception as e:
            # 안전 우선: 리스크 상태를 못 읽으면 차단 쪽으로 판단
            logger.error("kill_switch 조회 실패 — 안전상 차단: %s", e)
            return True

    def check(self, trade_date: str, stk_cd: str, notional: int) -> RiskDecision:
        """주문 1건 사전 검사. allowed=False 면 집행 금지."""
        if self.kill_switch_on():
            return RiskDecision(False, "kill_switch ON")

        # TODO: 일일 주문수/종목당 비중/일일 손실 한도 검사 (risk_state 기반)
        if notional > self.cfg.MAX_NOTIONAL_PER_NAME:
            return RiskDecision(False, f"종목당 한도 초과: {notional}")

        return RiskDecision(True)

    def trip_circuit_breaker(self, reason: str) -> None:
        """서킷브레이커 발동 — 킬스위치 ON 으로 당일 전체 정지."""
        logger.error("서킷브레이커 발동: %s", reason)
        risk_repo.set_kill_switch(True, reason)
