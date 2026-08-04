"""모니터 탭 실시간 시세 스트림(core/price_stream.py) 테스트 — 표시 전용 경로의 계약을 고정한다.

핵심 보장 (DB·네트워크 없이 fake 로 검증, conftest 철학 동일):
  1. **구독자가 있을 때만 WS 가 살아 있다** — 마지막 구독자가 떠나고 idle 이 지나면 피드를 닫는다.
     (워커 세션과 겹치는 시간을 '모니터 탭을 보는 동안'으로 한정하려는 설계 이유가 여기 있다)
  2. 틱이 있으면 REST 를 부르지 않고, 틱이 없으면 REST 로 폴백하되 **종목당 TTL 간격**으로만 부른다
     (1초 푸시가 REST 를 초당 두드리면 안 된다)
  3. 보드 판정은 `get_display_price` 와 동일 — 정규장=KRX / 그 밖=NXT 가능 종목만 NXT
  4. 스트림이 멈춘 뒤 남은 스냅샷은 `fresh_prices()` 가 걸러낸다(`/monitor` 폴링이 stale 가격을
     그대로 쓰면 안 된다)
"""
import time

import pytest

from core import price_stream as ps


# ── 가짜 협력 객체 ─────────────────────────────────────────────

class FakeFeed:
    """KiwoomRealtimeFeed 대역. 보드별 가격을 미리 심어두고 조회를 센다."""

    def __init__(self, symbols=None, px=None):
        self._symbols = dict(symbols or {})
        self._px = dict(px or {})       # (코드, 보드) → 가격
        self.stopped = False
        self.asked = []                 # get_fresh 인자 기록

    def get_fresh(self, stk_cd, prefer_nxt):
        self.asked.append((stk_cd, prefer_nxt))
        return self._px.get((stk_cd, "NXT" if prefer_nxt else "KRX"))

    def age(self, stk_cd, prefer_nxt):
        return 0.3

    def set_symbols(self, symbols):
        self._symbols = dict(symbols)

    def stats(self):
        return {"connected": True, "ticks": 7, "reconnects": 0, "symbols": len(self._symbols),
                "last_tick_age": 0.3, "error": None}

    def stop(self):
        self.stopped = True


class FakeData:
    """KiwoomDataClient 대역 — REST 폴백 호출 횟수를 센다."""

    def __init__(self, price=10000, is_nxt=False, nxt_enabled=True):
        self._price = price
        self._is_nxt = is_nxt
        self._nxt_enabled = nxt_enabled
        self.display_calls = []

    def get_display_price(self, stk_cd):
        self.display_calls.append(stk_cd)
        return self._price, self._is_nxt

    def is_nxt_enabled(self, stk_cd):
        return self._nxt_enabled


def _stream(feed=None, data=None, **kw):
    """fake 를 주입한 PriceStream. 기본은 '정규장 아님'(NXT 보드 우선)."""
    created = []

    def factory(symbols):
        f = feed or FakeFeed(symbols)
        f._symbols = dict(symbols)
        created.append(f)
        return f

    s = ps.PriceStream(feed_factory=factory,
                       data_client_factory=lambda: (data or FakeData()),
                       **kw)
    s._created = created  # 테스트 편의
    return s


@pytest.fixture(autouse=True)
def no_krx_session(monkeypatch):
    """기본 전제: 정규장 밖(= NXT 보드 우선). 정규장 케이스는 개별 테스트에서 덮어쓴다."""
    monkeypatch.setattr(ps, "_in_krx_session", lambda *a, **k: False)


@pytest.fixture
def one_position(monkeypatch):
    monkeypatch.setattr(ps.position_repo, "get_open_positions",
                        lambda: [{"stk_cd": "000001", "qty": 3, "avg_price": 9000}])


# ── 1. 구독자 수명주기 ─────────────────────────────────────────

def test_disabled_never_starts_feed():
    s = _stream(enabled=False)
    assert s.acquire() is False, "비활성 설정이면 구독을 거절한다"
    assert s._thread is None and s._created == []


def test_feed_starts_on_first_subscriber_and_stops_when_idle(one_position):
    s = _stream(push_sec=0.02, idle_sec=0.05)
    assert s.acquire() is True
    deadline = time.time() + 3
    while not s._created and time.time() < deadline:
        time.sleep(0.01)
    assert s._created, "구독자가 생기면 WS 피드를 띄운다"
    feed = s._created[0]

    s.release()
    deadline = time.time() + 3
    while s._thread is not None and time.time() < deadline:
        time.sleep(0.01)
    assert feed.stopped, "마지막 구독자가 떠나고 idle 이 지나면 WS 세션을 닫는다"
    assert s.stats()["ws"] is None


def test_reacquire_during_idle_keeps_session(one_position):
    """유예 시간 안에 다시 붙으면(새로고침·탭 전환) 세션을 닫지 않는다."""
    s = _stream(push_sec=0.02, idle_sec=5)
    s.acquire()
    deadline = time.time() + 3
    while not s._created and time.time() < deadline:
        time.sleep(0.01)
    feed = s._created[0]
    s.release()
    assert s.acquire() is True
    time.sleep(0.1)
    assert not feed.stopped and s._thread is not None
    assert s.stats()["subscribers"] == 1


# ── 2. 가격 출처: WS 우선, REST 는 TTL 간격 ────────────────────

def test_ws_tick_wins_and_skips_rest():
    feed = FakeFeed(px={("000001", "NXT"): 12345})
    data = FakeData(price=11111)
    s = _stream(data=data)
    prices = s._build_prices(data, feed, [{"stk_cd": "000001"}])
    assert prices["000001"] == {"prc": 12345, "is_nxt": True, "src": "ws", "age": 0.3}
    assert data.display_calls == [], "틱이 있으면 REST 를 부르지 않는다"


def test_rest_fallback_when_no_tick_is_throttled():
    feed = FakeFeed(px={})               # 무틱(하한가·NXT 미상장·세션 공백)
    data = FakeData(price=11111, is_nxt=False)
    s = _stream(data=data, rest_ttl_sec=60)
    pos = [{"stk_cd": "000001"}]
    first = s._build_prices(data, feed, pos)
    assert first["000001"]["prc"] == 11111 and first["000001"]["src"] == "rest"
    for _ in range(5):                   # 1초 푸시 5회
        s._build_prices(data, feed, pos)
    assert data.display_calls == ["000001"], "REST 폴백은 종목당 TTL 간격으로만 부른다"


def test_rest_ttl_expiry_refetches():
    feed = FakeFeed(px={})
    data = FakeData()
    s = _stream(data=data, rest_ttl_sec=0.01)
    s._build_prices(data, feed, [{"stk_cd": "000001"}])
    time.sleep(0.02)
    s._build_prices(data, feed, [{"stk_cd": "000001"}])
    assert len(data.display_calls) == 2


def test_no_price_at_all_omits_symbol():
    """틱도 REST 도 없으면 그 종목은 스냅샷에서 빠진다 → 프론트는 폴링 값을 유지한다."""
    feed = FakeFeed(px={})
    data = FakeData(price=0)
    s = _stream(data=data)
    assert s._build_prices(data, feed, [{"stk_cd": "000001"}]) == {}


# ── 3. 보드 판정은 get_display_price 와 동일 ────────────────────

def test_board_follows_krx_session(monkeypatch):
    feed = FakeFeed(px={("000001", "KRX"): 500, ("000001", "NXT"): 505})
    data = FakeData()
    s = _stream(data=data)
    assert s._build_prices(data, feed, [{"stk_cd": "000001"}])["000001"]["prc"] == 505

    monkeypatch.setattr(ps, "_in_krx_session", lambda *a, **k: True)
    s2 = _stream(data=data)
    got = s2._build_prices(data, feed, [{"stk_cd": "000001"}])["000001"]
    assert got["prc"] == 500 and got["is_nxt"] is False, "정규장엔 KRX 보드를 본다"


def test_nxt_disabled_stock_uses_krx_board():
    feed = FakeFeed(px={("000001", "KRX"): 500, ("000001", "NXT"): 505})
    data = FakeData(nxt_enabled=False)
    s = _stream(data=data)
    got = s._build_prices(data, feed, [{"stk_cd": "000001"}])["000001"]
    assert got["prc"] == 500 and got["is_nxt"] is False


def test_feed_exception_falls_back_to_rest():
    class BrokenFeed(FakeFeed):
        def get_fresh(self, stk_cd, prefer_nxt):
            raise RuntimeError("ws 이상")

    data = FakeData(price=777)
    s = _stream(data=data)
    got = s._build_prices(data, BrokenFeed(), [{"stk_cd": "000001"}])["000001"]
    assert got == {"prc": 777, "is_nxt": False, "src": "rest", "age": 0.0}


# ── 4. 정지 후 남은 스냅샷 차단 ────────────────────────────────

def test_fresh_prices_rejects_stale_snapshot():
    s = _stream()
    s._snapshot = {"seq": 1, "at": time.time(), "prices": {"000001": {"prc": 100}}}
    assert s.fresh_prices()["000001"]["prc"] == 100
    s._snapshot = {"seq": 1, "at": time.time() - 30, "prices": {"000001": {"prc": 100}}}
    assert s.fresh_prices() == {}, "스트림이 멈춘 뒤 남은 가격을 폴링이 쓰면 안 된다"


def test_fresh_prices_empty_before_first_snapshot():
    assert _stream().fresh_prices() == {}
