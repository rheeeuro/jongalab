"""monitor.check_once 견고성 테스트 — 유지보수 단계 실패가 감시를 멈추지 못한다.

회귀 방지: 과거 reconcile_dead_sent 의 멱등키 충돌(Duplicate entry) 예외가 check_once
전체를 매 폴링 중단시켜, 하드손절/스탑 감시가 모든 종목에서 멈췄다(보유 잔량 무방비).
유지보수(체결동기화/미체결취소/죽은주문정리)는 격리돼, 한 단계가 던져도 손절/스탑 점검은
반드시 돌아야 한다. DB·네트워크 없이 fake 로 검증한다(conftest 철학 동일).
"""
from datetime import datetime

import pytest

from workers import monitor
from core.config import HARD_STOP_LOSS_PCT


class FakeData:
    def __init__(self, price):
        self._price = price

    def get_market_price(self, stk_cd):
        return self._price


class FakeEngine:
    """check_once 가 쓰는 최소 표면만: client(유지보수 인자), data, execute_sell."""

    def __init__(self, price):
        self.client = object()
        self.data = FakeData(price)
        self.sells = []

    def execute_sell(self, trade_date, stk_cd, qty, price, dmst_stex_tp=None, tag=None):
        self.sells.append(dict(stk_cd=stk_cd, qty=qty, price=price, tag=tag))
        return True


@pytest.fixture
def patched(monkeypatch):
    """유지보수 함수·repository 를 fake 로 교체. 보유 1종목은 하드손절선 아래로 가격 설정."""
    avg = 10000
    cur = round(avg * (1 - HARD_STOP_LOSS_PCT / 100)) - 1  # 하드손절 발동가
    pos = {"stk_cd": "000001", "qty": 7, "avg_price": avg}

    monkeypatch.setattr(monitor, "sync_fills", lambda client: None)
    monkeypatch.setattr(monitor, "cancel_stale_orders", lambda client: 0)
    monkeypatch.setattr(monitor.plan_repo, "get_active_plans", lambda: [])
    monkeypatch.setattr(monitor.position_repo, "get_open_positions", lambda: [dict(pos)])
    monkeypatch.setattr(monitor.position_repo, "get_position", lambda stk_cd: None)  # 청산 확인
    monkeypatch.setattr(monitor.audit_log, "append", lambda *a, **k: None)

    return FakeEngine(cur)


def test_reconcile_failure_does_not_block_hardstop(patched, monkeypatch):
    """죽은주문 정리가 예외를 던져도 check_once 는 끝까지 돌아 하드손절을 집행한다."""
    def boom(client):
        raise RuntimeError("1062 (23000): Duplicate entry '...:dead' for key 'idempotency_key'")

    monkeypatch.setattr(monitor, "reconcile_dead_sent", boom)

    monitor.check_once(patched)  # 예외 전파되면 테스트 실패

    assert len(patched.sells) == 1, "유지보수 실패에도 하드손절 매도가 집행돼야 한다"
    assert patched.sells[0]["tag"] == "hardstop"
    assert patched.sells[0]["qty"] == 7


def test_all_maintenance_failing_still_monitors(patched, monkeypatch):
    """세 유지보수 단계가 모두 던져도 감시는 정상 동작한다."""
    def boom(client):
        raise RuntimeError("maintenance down")

    monkeypatch.setattr(monitor, "sync_fills", boom)
    monkeypatch.setattr(monitor, "cancel_stale_orders", boom)
    monkeypatch.setattr(monitor, "reconcile_dead_sent", boom)

    monitor.check_once(patched)

    assert len(patched.sells) == 1
    assert patched.sells[0]["tag"] == "hardstop"
