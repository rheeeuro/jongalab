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
from core.repository import position as position_repo

logger = logging.getLogger("RiskEngine")


class RiskConfig:
    """리스크 한도 파라미터. 클래스 속성은 기본값이며, load_from_db()로 대시보드 설정을 덮어쓴다."""
    MAX_ORDERS_PER_DAY = 10
    MAX_NOTIONAL_PER_NAME = 5_000_000      # 종목당 최대 명목금액(원)
    MAX_DAILY_LOSS = 3_000_000             # 일일 최대 손실(원) → 초과 시 서킷브레이커
    MAX_POSITIONS = 5

    def load_from_db(self) -> "RiskConfig":
        """risk_config 테이블(대시보드 설정)에서 한도를 로드해 인스턴스에 반영."""
        from core.repository import risk_config as repo
        cfg = repo.get_risk_config()
        self.MAX_ORDERS_PER_DAY = cfg["MAX_ORDERS_PER_DAY"]
        self.MAX_NOTIONAL_PER_NAME = cfg["MAX_NOTIONAL_PER_NAME"]
        self.MAX_DAILY_LOSS = cfg["MAX_DAILY_LOSS"]
        self.MAX_POSITIONS = cfg["MAX_POSITIONS"]
        return self


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskEngine:
    def __init__(self, cfg: RiskConfig | None = None):
        if cfg is None:
            cfg = RiskConfig()
            try:
                cfg.load_from_db()  # 대시보드 설정 반영(없으면 기본값)
            except Exception as e:
                logger.warning("리스크 설정 DB 로드 실패 — 기본값 사용: %s", e)
        self.cfg = cfg

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
        """매수 주문 1건 사전 검사. allowed=False 면 집행 금지.

        검사 순서: 킬스위치 → 종목당 명목 → 일일 손실(초과 시 브레이커) →
        일일 주문수 → 동시 보유 종목수(신규 종목만).
        """
        # 1. 킬스위치 (env OR DB)
        if self.kill_switch_on():
            return RiskDecision(False, "kill_switch ON")

        # 2. 종목당 명목 한도
        if notional > self.cfg.MAX_NOTIONAL_PER_NAME:
            return RiskDecision(False, f"종목당 한도 초과: {notional} > {self.cfg.MAX_NOTIONAL_PER_NAME}")

        state = risk_repo.get_state(trade_date) or {}

        # 3. 일일 손실 한도 → 초과 시 서킷브레이커 발동 후 차단
        realized = state.get("realized_pnl") or 0
        if realized <= -self.cfg.MAX_DAILY_LOSS:
            self.trip_circuit_breaker(
                f"일일 손실 한도 초과: {realized} <= -{self.cfg.MAX_DAILY_LOSS}", trade_date
            )
            return RiskDecision(False, "일일 손실 한도 초과 (서킷브레이커)")

        # 4. 일일 주문 건수 한도
        orders = state.get("orders_count") or 0
        if orders >= self.cfg.MAX_ORDERS_PER_DAY:
            return RiskDecision(False, f"일일 주문수 한도 초과: {orders} >= {self.cfg.MAX_ORDERS_PER_DAY}")

        # 5. 동시 보유 종목수 한도 (이미 보유 중인 종목 추가매수는 제외)
        try:
            held = {p["stk_cd"] for p in position_repo.get_open_positions()}
        except Exception as e:
            logger.error("포지션 조회 실패 — 안전상 차단: %s", e)
            return RiskDecision(False, "포지션 조회 실패")
        if stk_cd not in held and len(held) >= self.cfg.MAX_POSITIONS:
            return RiskDecision(False, f"보유 종목수 한도 초과: {len(held)} >= {self.cfg.MAX_POSITIONS}")

        return RiskDecision(True)

    def record_order(self, trade_date: str, n: int = 1) -> None:
        """주문 전송 성공 후 일일 주문 건수를 증가시킨다(한도 카운팅)."""
        risk_repo.increment_orders(trade_date, n)

    def trip_circuit_breaker(self, reason: str, trade_date: str | None = None) -> None:
        """서킷브레이커 발동 — 킬스위치 ON 으로 당일 전체 정지 + 일자 플래그 기록."""
        logger.error("서킷브레이커 발동: %s", reason)
        risk_repo.set_kill_switch(True, reason)
        if trade_date:
            risk_repo.set_breaker(trade_date, True)
