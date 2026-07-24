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

    def is_nxt_enabled(self, stk_cd):
        # resolve_sell_venue 가 KRX 장외 시간대에 조회 — True 라야 어느 시각에 돌아도 매도 가능
        return True


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
    # 뉴스 베토·알림은 jongalab DB/텔레그램을 타므로 fake — 기존 하드손절 테스트는 베토 무발동
    monkeypatch.setattr(monitor.news_veto, "get_severe_verdicts", lambda: {})
    monkeypatch.setattr(monitor, "notify_admin", lambda msg: 0)

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


# ── 오버나잇 US 결과로 하드손절 강화 (effective_hard_stop_pct) ──

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _reset_us_tighten(monkeypatch):
    """모듈 캐시(프로세스당 1회 계산)가 테스트 간 새지 않게 리셋 + 기본은 네트워크 없이 base pct."""
    monitor._us_tighten_cache.update(computed=False, pct=None)

    def _no_net(*a, **k):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(monitor.requests, "get", _no_net)
    yield
    monitor._us_tighten_cache.update(computed=False, pct=None)


def _us_resp(monkeypatch, **regs):
    """monitor.requests.get 을 US 정규장 등락(regular_ret) 응답으로 대체."""
    data = {sym: {"regular_ret": regs.get(sym), "extended_ret": None, "market_state": "CLOSED"}
            for sym in ("SOXX", "SKHY", "EWY", "KORU")}
    monkeypatch.setattr(monitor.requests, "get", lambda *a, **k: _FakeResp(data))


def test_overnight_intensity_ramp():
    b = monitor.FUTURES_FLAT_BAND
    assert monitor._overnight_intensity(None) == 0.0
    assert monitor._overnight_intensity(1.0) == 0.0          # 상승
    assert monitor._overnight_intensity(-b) == 0.0           # 보합밴드 경계
    assert monitor._overnight_intensity(-monitor.FUTURES_FULL_CUT_PCT - 5) == 1.0  # 급락 → 상한
    assert 0.0 < monitor._overnight_intensity(-1.0) < 1.0


def test_effective_hard_stop_no_change_when_up(monkeypatch):
    _us_resp(monkeypatch, SOXX=1.0, SKHY=0.8, EWY=0.5, KORU=1.5)
    assert monitor.effective_hard_stop_pct() == HARD_STOP_LOSS_PCT  # 상승 밤 → 기본


def test_effective_hard_stop_tightens_on_semis_crash(monkeypatch):
    # 반도체(SOXX/SKHY) 급락 밤 → 손절 폭이 기본보다 좁아지고 하한 이상
    _us_resp(monkeypatch, SOXX=-3.0, SKHY=-2.5, EWY=-0.2, KORU=-0.3)
    pct = monitor.effective_hard_stop_pct()
    assert monitor.US_STOP_MIN_PCT <= pct < HARD_STOP_LOSS_PCT


def test_effective_hard_stop_floor(monkeypatch):
    # 초급락이어도 US_STOP_MIN_PCT 밑으로는 안 내려간다
    _us_resp(monkeypatch, SOXX=-20.0, SKHY=-20.0, EWY=-20.0, KORU=-60.0)
    assert monitor.effective_hard_stop_pct() == monitor.US_STOP_MIN_PCT


def test_effective_hard_stop_koru_normalized(monkeypatch):
    # KORU(3x)는 /3 정규화 — KORU -3% 만으로는 EWY -1% 상당(약한 강도)이라 큰 컷 안 남
    _us_resp(monkeypatch, SOXX=0.5, SKHY=0.5, EWY=None, KORU=-3.0)
    pct = monitor.effective_hard_stop_pct()
    assert pct < HARD_STOP_LOSS_PCT  # 약하게라도 강화
    # KORU/3 = -1% 강도 < 반도체 -3% 강도였을 때보다 덜 좁혀짐(경계만 확인)
    assert pct > monitor.US_STOP_MIN_PCT


def test_effective_hard_stop_fetch_fail_keeps_base(monkeypatch):
    # autouse 픽스처가 이미 no-net → 취득 실패 시 기본값 유지
    assert monitor.effective_hard_stop_pct() == HARD_STOP_LOSS_PCT


def test_effective_hard_stop_disabled(monkeypatch):
    monkeypatch.setattr(monitor, "US_STOP_TIGHTEN_ENABLED", False)
    _us_resp(monkeypatch, SOXX=-5.0, SKHY=-5.0, EWY=-5.0, KORU=-15.0)
    assert monitor.effective_hard_stop_pct() == HARD_STOP_LOSS_PCT  # 비활성 → 미개입
