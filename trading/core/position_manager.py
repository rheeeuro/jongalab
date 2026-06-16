"""포지션 관리 — 체결 반영, 손익 산출, 청산 후보 판정.

첫 범위(종가베팅)에서는 장중 상시 손절 감시 대신 settle 워커가 사이클 단위로 청산한다.
"""
import logging

from core.repository import position as position_repo

logger = logging.getLogger("PositionManager")


class PositionManager:
    def open_positions(self) -> list[dict]:
        return position_repo.get_open_positions()

    def unrealized_pnl(self, position: dict, cur_price: int) -> int:
        """미실현 손익(원) = (현재가 - 평단) * 수량."""
        return (cur_price - position["avg_price"]) * position["qty"]

    def liquidation_candidates(self, price_map: dict[str, int]) -> list[dict]:
        """청산 대상 판정. TODO: 익절/손절 임계값 기준 구현."""
        raise NotImplementedError("청산 판정 미구현 (스켈레톤)")
