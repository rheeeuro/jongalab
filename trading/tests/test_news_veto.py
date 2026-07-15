"""뉴스 베토 강제청산 테스트 — severe 판정 종목의 개장 즉시 전량매도와 fail-safe.

핵심 보장 (DB·네트워크 없이 fake 로 검증, conftest 철학 동일):
  1. severe 판정 보유 종목은 가격 무관(하드손절 미달이어도) tag='newsveto' 전량매도 + plan 해제
  2. 베토 조회가 빈 dict/예외여도 기존 하드손절 감시는 그대로 돈다(fail-safe 회귀 방지)
  3. 비보유 종목 판정은 아무것도 하지 않는다
  4. NXT 불가 + KRX 개장 전이면 매도 보류(plan 유지) — 09:00 이후 폴링에서 청산
"""
from datetime import datetime

import pytest

from workers import monitor
from core import news_veto
from core.config import HARD_STOP_LOSS_PCT


class FakeData:
    def __init__(self, price, nxt_enabled=True):
        self._price = price
        self._nxt = nxt_enabled

    def get_market_price(self, stk_cd):
        return self._price

    def is_nxt_enabled(self, stk_cd):
        return self._nxt


class FakeEngine:
    def __init__(self, price, nxt_enabled=True):
        self.client = object()
        self.data = FakeData(price, nxt_enabled)
        self.sells = []

    def execute_sell(self, trade_date, stk_cd, qty, price, dmst_stex_tp=None, tag=None):
        self.sells.append(dict(stk_cd=stk_cd, qty=qty, price=price,
                               venue=dmst_stex_tp, tag=tag))
        return True


VETO = {"stk_cd": "000001", "stk_nm": "테스트제약", "confidence": 92,
        "category": "임상실패", "reason": "FDA 승인 반려(CRL) 보도"}


@pytest.fixture
def patched(monkeypatch):
    """보유 1종목(000001). 가격은 평단과 동일(하드손절 미발동) — 베토만이 매도 사유가 되게."""
    avg = 10000
    pos = {"stk_cd": "000001", "qty": 7, "avg_price": avg}
    plan = {"stk_cd": "000001", "trade_date": "20260715", "stop_price": 1}
    deactivated = []

    monkeypatch.setattr(monitor, "sync_fills", lambda client: None)
    monkeypatch.setattr(monitor, "cancel_stale_orders", lambda client: 0)
    monkeypatch.setattr(monitor, "reconcile_dead_sent", lambda client: 0)
    monkeypatch.setattr(monitor.plan_repo, "get_active_plans", lambda: [dict(plan)])
    monkeypatch.setattr(monitor.plan_repo, "deactivate",
                        lambda trade_date, stk_cd, note: deactivated.append((stk_cd, note)))
    monkeypatch.setattr(monitor.plan_repo, "raise_stop", lambda *a, **k: False)
    monkeypatch.setattr(monitor.position_repo, "get_open_positions", lambda: [dict(pos)])
    monkeypatch.setattr(monitor.position_repo, "get_position", lambda stk_cd: None)  # 청산 확인
    monkeypatch.setattr(monitor.audit_log, "append", lambda *a, **k: None)
    monkeypatch.setattr(monitor, "notify_admin", lambda msg: 0)
    monkeypatch.setattr(monitor.news_veto, "get_severe_verdicts",
                        lambda: {"000001": dict(VETO)})

    engine = FakeEngine(avg)  # 평단 그대로 = 하드손절/스탑 모두 미발동
    engine.deactivated = deactivated
    return engine


def test_severe_verdict_sells_full_qty_price_independent(patched):
    """severe 판정이면 하드손절선 위 가격이어도 전량매도(tag=newsveto)하고 plan 을 해제한다."""
    monitor.check_once(patched)

    assert len(patched.sells) == 1
    sell = patched.sells[0]
    assert sell["tag"] == "newsveto"
    assert sell["qty"] == 7, "전량 매도여야 한다(반매도 아님)"
    assert patched.deactivated and patched.deactivated[0][0] == "000001"


def test_veto_precedes_hardstop(patched):
    """하드손절선 아래로 이미 갭하락한 상태여도 매도 태그는 newsveto(0순위)다."""
    patched.data._price = round(10000 * (1 - HARD_STOP_LOSS_PCT / 100)) - 1

    monitor.check_once(patched)

    assert len(patched.sells) == 1
    assert patched.sells[0]["tag"] == "newsveto"


def test_empty_vetoes_keeps_hardstop_working(patched, monkeypatch):
    """베토 조회가 빈 dict 여도(비활성/조회 실패) 하드손절 감시는 그대로 동작한다."""
    monkeypatch.setattr(monitor.news_veto, "get_severe_verdicts", lambda: {})
    patched.data._price = round(10000 * (1 - HARD_STOP_LOSS_PCT / 100)) - 1

    monitor.check_once(patched)

    assert len(patched.sells) == 1
    assert patched.sells[0]["tag"] == "hardstop"


def test_verdict_for_non_held_stock_is_ignored(patched, monkeypatch):
    """비보유 종목의 severe 판정은 아무 매도도 일으키지 않는다."""
    monkeypatch.setattr(monitor.news_veto, "get_severe_verdicts",
                        lambda: {"999999": dict(VETO, stk_cd="999999")})

    monitor.check_once(patched)

    assert patched.sells == []


def test_no_venue_holds_position(patched, monkeypatch):
    """NXT 불가 종목 + KRX 개장 전(08:30)이면 매도 보류 — plan 도 유지된다."""
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 15, 8, 30)

    monkeypatch.setattr(monitor, "datetime", FakeDT)
    patched.data._nxt = False

    monitor.check_once(patched)

    assert patched.sells == []
    assert patched.deactivated == []


def test_fetch_error_returns_empty(monkeypatch):
    """jongalab DB 조회 실패 시 빈 dict(미개입)이고 캐시를 남기지 않는다."""
    monkeypatch.setattr(news_veto, "_cache", None)
    def boom(verdict_date):
        raise RuntimeError("jongalab DB down")
    monkeypatch.setattr(news_veto, "fetch_severe_verdicts", boom)

    assert news_veto.get_severe_verdicts() == {}
    assert news_veto._cache is None, "실패는 캐시하지 않아 다음 폴링에 즉시 재조회돼야 한다"


def test_fetch_success_is_cached(monkeypatch):
    """성공 조회는 TTL 캐시돼 폴링마다 jongalab DB 를 때리지 않는다."""
    monkeypatch.setattr(news_veto, "_cache", None)
    calls = []

    def fetch(verdict_date):
        calls.append(verdict_date)
        return {"000001": dict(VETO)}

    monkeypatch.setattr(news_veto, "fetch_severe_verdicts", fetch)

    first = news_veto.get_severe_verdicts()
    second = news_veto.get_severe_verdicts()

    assert first == second and "000001" in first
    assert len(calls) == 1, "TTL 내 재호출은 캐시를 써야 한다"
