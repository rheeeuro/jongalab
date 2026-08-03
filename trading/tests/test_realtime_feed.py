"""실시간 WS 피드 + 틱 판정 테스트 — 자금 경로의 fail-safe 를 고정한다.

핵심 보장 (DB·네트워크 없이 fake 로 검증, conftest 철학 동일):
  1. TTL 초과·미구독·다른 보드 → get_fresh 가 None → 호출부가 REST 로 폴백한다
     (조용히 끊긴 WS 의 stale 가격으로 손절이 미발동하는 최악 실패 방지)
  2. 피드를 안 붙이면 KiwoomDataClient 는 종전과 동일하게 전부 REST
  3. 틱 판정은 하드손절을 즉시 집행하되, **트레일링 상향은 하지 않는다**
     (TRAIL_PCT 는 15초 주기로 튜닝된 값 — 상향 주기가 바뀌면 실효 파라미터가 바뀐다)
  4. 매도 재시도 쿨다운: 틱이 쏟아져도 주문 전송은 SELL_RETRY_COOLDOWN_SEC 간격
     (2026-07-10 HLB 하한가 거부 238건 → 초당 재시도로 폭증하는 것을 막는다)
"""
import time

import pytest

from core.kiwoom_data_client import KiwoomDataClient
from core.realtime_feed import KiwoomRealtimeFeed, nxt_symbol
from core.config import HARD_STOP_LOSS_PCT
from workers import monitor


# ── 1. 피드 캐시 신선도 ──────────────────────────────────────

def _feed_with_tick(item: str, price: int, board: str, age: float = 0.0):
    feed = KiwoomRealtimeFeed(symbols={"000001": True})
    feed._on_real({"trnm": "REAL", "data": [
        {"type": "0B", "item": item, "values": {"10": f"+{price}", "9081": board}}]})
    if age:
        code = item[:-3] if item.endswith("_NX") else item
        p, ts = feed._px[(code, board)]
        feed._px[(code, board)] = (p, ts - age)
    return feed


def test_fresh_tick_is_returned_per_board():
    feed = _feed_with_tick(nxt_symbol("000001"), 12345, "NXT")
    assert feed.get_fresh("000001", prefer_nxt=True) == 12345
    # 보드가 다르면 폴백하지 않는다 — 잘못된 보드 가격으로 손절 판정하면 안 된다
    assert feed.get_fresh("000001", prefer_nxt=False) is None


def test_stale_tick_returns_none():
    feed = _feed_with_tick("000001", 12345, "KRX", age=999)
    assert 999 > feed._ttl, "테스트 전제: 999초는 TTL 보다 오래됐다"
    assert feed.get_fresh("000001", prefer_nxt=False) is None, "TTL 초과면 REST 폴백해야 한다"


def test_unknown_stock_returns_none():
    feed = _feed_with_tick("000001", 12345, "KRX")
    assert feed.get_fresh("999999", prefer_nxt=False) is None


def test_negative_sign_price_is_absolute():
    """키움 현재가는 전일대비 부호가 붙는다(-1718000) — 가격은 절대값이어야 한다."""
    feed = KiwoomRealtimeFeed(symbols={"000660": False})
    feed._on_real({"trnm": "REAL", "data": [
        {"type": "0B", "item": "000660", "values": {"10": "-1718000", "9081": "KRX"}}]})
    assert feed.get_fresh("000660", prefer_nxt=False) == 1718000


def test_fill_notification_sets_signal_once():
    feed = KiwoomRealtimeFeed(symbols={})
    assert feed.take_fill_signal() is False
    feed._on_real({"trnm": "REAL", "data": [{"type": "00", "item": "", "values": {}}]})
    assert feed.take_fill_signal() is True
    assert feed.take_fill_signal() is False, "소비 후에는 다시 False(중복 동기화 방지)"


def test_item_over_limit_is_capped():
    """등록 상한(키움 ≈97건)을 넘기지 않는다 — 초과 REG 는 거부된다."""
    feed = KiwoomRealtimeFeed(symbols={f"{i:06d}": True for i in range(80)})
    assert len(feed._items()) <= 90


# ── 1-b. 수급 관측(0B 부가 필드 + 0w) — 수집 전용이라 판정에 영향이 없어야 한다 ──

def test_supply_fields_parsed_from_trade_tick():
    """0B 틱의 체결강도·매수/매도 체결량이 수급 스냅샷으로 들어간다(추가 구독 없이)."""
    feed = KiwoomRealtimeFeed(symbols={"005930": False}, subscribe_supply=True)
    feed._on_real({"trnm": "REAL", "data": [{"type": "0B", "item": "005930", "values": {
        "10": "-244000", "9081": "KRX", "228": "78.13",
        "1030": "4867438", "1031": "3802879", "1032": "-43.86"}}]})
    s = feed.get_supply("005930", prefer_nxt=False)
    assert s["cntr_str"] == "78.13" and s["sell_qty"] == "4867438"
    assert s["buy_qty"] == "3802879" and s["buy_ratio"] == "-43.86"
    assert s["board"] == "KRX" and "age_sec" in s


def test_program_tick_merges_and_never_moves_price():
    """0w(프로그램매매)는 수급에만 병합되고 가격·틱 이벤트는 건드리지 않는다."""
    feed = KiwoomRealtimeFeed(symbols={"005930": False}, subscribe_supply=True)
    feed._on_real({"trnm": "REAL", "data": [{"type": "0B", "item": "005930", "values": {
        "10": "+244000", "9081": "KRX", "228": "78.13"}}]})
    feed._tick_event.clear()
    feed._on_real({"trnm": "REAL", "data": [{"type": "0w", "item": "005930", "values": {
        "10": "+999999", "202": "3798971", "206": "1800396",
        "210": "-1998575", "212": "-488867"}}]})

    assert feed.get_fresh("005930", prefer_nxt=False) == 244000, "0w 가 가격을 덮어쓰면 안 된다"
    assert feed._tick_event.is_set() is False, "0w 로 틱 대기가 깨지면 판정 주기가 바뀐다"
    s = feed.get_supply("005930", prefer_nxt=False)
    assert s["prm_net_qty"] == "-1998575" and s["cntr_str"] == "78.13", "0B+0w 가 한 스냅샷"


def test_supply_absent_when_disabled():
    """토글을 끄면 0B 부가 필드도 수집하지 않는다(구독 등록도 안 함)."""
    feed = KiwoomRealtimeFeed(symbols={"005930": False}, subscribe_supply=False)
    feed._on_real({"trnm": "REAL", "data": [{"type": "0B", "item": "005930", "values": {
        "10": "+244000", "9081": "KRX", "228": "78.13"}}]})
    assert feed.get_supply("005930", prefer_nxt=False) is None
    assert feed.get_fresh("005930", prefer_nxt=False) == 244000, "가격은 그대로 동작"


def test_supply_snapshot_failure_does_not_break_evaluation():
    """수급 조회가 터져도 매도 판정 payload 는 만들어진다(관측은 자금 경로에 개입 금지)."""
    class Boom:
        def get_supply(self, stk_cd, prefer_nxt):
            raise RuntimeError("feed down")

    state = monitor.MonitorState()
    state.feed = Boom()
    from datetime import datetime
    assert monitor._supply_snapshot(state, "005930", datetime.now()) == {}


# ── 2. 피드 미주입 시 종전 동작 ────────────────────────────────

def test_data_client_without_feed_uses_rest(monkeypatch):
    client = KiwoomDataClient()
    calls = []
    monkeypatch.setattr(client, "get_display_price", lambda s: (calls.append(s), (7777, False))[1])
    assert client.get_market_price("000001") == 7777
    assert calls == ["000001"], "피드가 없으면 REST 경로 그대로"


def test_data_client_falls_back_when_feed_stale(monkeypatch):
    client = KiwoomDataClient()
    client.attach_feed(_feed_with_tick("000001", 111, "KRX", age=999))
    monkeypatch.setattr(client, "get_display_price", lambda s: (7777, False))
    assert client.get_market_price("000001") == 7777


def test_data_client_falls_back_when_feed_raises(monkeypatch):
    class Boom:
        def get_fresh(self, stk_cd, prefer_nxt):
            raise RuntimeError("feed broken")

    client = KiwoomDataClient()
    client.attach_feed(Boom())
    monkeypatch.setattr(client, "get_display_price", lambda s: (7777, False))
    assert client.get_market_price("000001") == 7777, "피드 예외가 시세 조회를 막지 않는다"


# ── 3·4. 틱 판정 — 하드손절 즉시 / 트레일링 제외 / 쿨다운 ──────────

AVG = 10000
BREACH = round(AVG * (1 - HARD_STOP_LOSS_PCT / 100)) - 1


class FakeData:
    def is_nxt_enabled(self, stk_cd):
        return True

    def get_market_price(self, stk_cd):
        return BREACH


class FakeEngine:
    def __init__(self, accepts=True):
        self.client = object()
        self.data = FakeData()
        self.sells = []
        self.accepts = accepts  # False = 키움 거부(하한가 매도 불가 상황)

    def execute_sell(self, trade_date, stk_cd, qty, price, dmst_stex_tp=None, tag=None):
        self.sells.append(dict(stk_cd=stk_cd, qty=qty, price=price, tag=tag))
        return self.accepts


class StubFeed:
    """가격만 돌려주는 최소 피드 — 판정 로직만 검증한다."""

    def __init__(self, price):
        self.price = price

    def get_fresh(self, stk_cd, prefer_nxt):
        return self.price


@pytest.fixture
def tick_env(monkeypatch):
    monkeypatch.setattr(monitor.audit_log, "append", lambda *a, **k: None)
    monkeypatch.setattr(monitor, "notify_admin", lambda msg: 0)
    monkeypatch.setattr(monitor.position_repo, "get_position", lambda stk_cd: None)  # 청산 확인
    monkeypatch.setattr(monitor.plan_repo, "deactivate", lambda *a, **k: None)
    raised = []
    monkeypatch.setattr(monitor.plan_repo, "raise_stop",
                        lambda *a, **k: (raised.append(a), True)[1])
    monkeypatch.setattr(monitor, "effective_hard_stop_pct", lambda: HARD_STOP_LOSS_PCT)

    state = monitor.MonitorState()
    state.positions = {"000001": {"stk_cd": "000001", "qty": 7, "avg_price": AVG}}
    state.plans = {"000001": {"stk_cd": "000001", "trade_date": "20260731", "stop_price": 1}}
    state.vetoes = {}
    return FakeEngine(), state, raised


def test_tick_fires_hardstop_immediately(tick_env):
    engine, state, _ = tick_env
    monitor.check_ticks(engine, state, StubFeed(BREACH))
    assert len(engine.sells) == 1
    assert engine.sells[0]["tag"] == "hardstop"
    assert engine.sells[0]["qty"] == 7


def test_tick_does_not_raise_trailing_stop(tick_env):
    """틱 경로는 스탑선을 올리지 않는다 — TRAIL_PCT 는 15초 주기 튜닝 값이다."""
    engine, state, raised = tick_env
    monitor.check_ticks(engine, state, StubFeed(AVG * 2))  # 손절·스탑 미발동, 상승 중
    assert engine.sells == []
    assert raised == [], "틱 경로에서 트레일링 상향이 일어나면 실효 TRAIL_PCT 가 좁아진다"


def test_slow_path_does_raise_trailing_stop(tick_env, monkeypatch):
    """반면 15초 경로(check_once)는 종전대로 상향한다."""
    engine, state, raised = tick_env
    monkeypatch.setattr(monitor, "sync_fills", lambda c: None)
    monkeypatch.setattr(monitor, "cancel_stale_orders", lambda c: 0)
    monkeypatch.setattr(monitor, "reconcile_dead_sent", lambda c: 0)
    monkeypatch.setattr(monitor.plan_repo, "get_active_plans",
                        lambda: [dict(state.plans["000001"])])
    monkeypatch.setattr(monitor.position_repo, "get_open_positions",
                        lambda: [dict(state.positions["000001"])])
    monkeypatch.setattr(monitor.news_veto, "get_severe_verdicts", lambda: {})
    monkeypatch.setattr(engine.data, "get_market_price", lambda s: AVG * 2)

    monitor.check_once(engine, state)

    assert engine.sells == []
    assert len(raised) == 1, "15초 경로는 종전대로 트레일링을 상향해야 한다"


def test_sell_retry_respects_cooldown(tick_env):
    """매도가 거부되는 하한가 상황에서 틱이 쏟아져도 주문 전송은 쿨다운 간격으로만.

    2026-07-10 HLB 하한가 때 15초 폴링으로도 거부가 238건 쌓였다. 판정 주기를 그대로
    주문에 물리면 시간당 수천 건이 되어 키움 유량 제한에 걸리고, 하한가가 풀리는 순간
    정작 주문이 막힌다. 거부라 포지션이 남아 매 틱 재발동 조건이 성립하는 경로다."""
    _, state, _ = tick_env
    engine = FakeEngine(accepts=False)
    feed = StubFeed(BREACH)
    for _ in range(50):  # 50틱 ≈ 삼성전자 1.5초분
        monitor.check_ticks(engine, state, feed)
    assert len(engine.sells) == 1, f"쿨다운이 재전송을 막아야 한다(실제 {len(engine.sells)}건)"
    assert state.cooldown_skips >= 40


def test_cooldown_expiry_allows_retry(tick_env):
    """쿨다운이 지나면 다시 시도한다 — 하한가 풀림 포착을 위해 재시도 자체는 유지한다."""
    _, state, _ = tick_env
    engine = FakeEngine(accepts=False)
    feed = StubFeed(BREACH)
    monitor.check_ticks(engine, state, feed)
    assert len(engine.sells) == 1
    # 쿨다운 경과를 시뮬레이션(마지막 전송 시각을 뒤로 당김)
    state.last_sell["000001"] = time.time() - monitor.SELL_RETRY_COOLDOWN_SEC - 1
    monitor.check_ticks(engine, state, feed)
    assert len(engine.sells) == 2


def test_confirmed_exit_stops_watching(tick_env):
    """매도가 체결 확인되면 스냅샷에서 빠져 헛 판정하지 않는다(재시도 자체가 없다)."""
    engine, state, _ = tick_env  # accepts=True + get_position→None = 청산 확인
    feed = StubFeed(BREACH)
    for _ in range(10):
        monitor.check_ticks(engine, state, feed)
    assert len(engine.sells) == 1
    assert "000001" not in state.positions


def test_tick_veto_precedes_hardstop(tick_env):
    engine, state, _ = tick_env
    state.vetoes = {"000001": {"stk_nm": "테스트", "category": "임상실패", "confidence": 92,
                               "reason": "CRL"}}
    monitor.check_ticks(engine, state, StubFeed(BREACH))
    assert len(engine.sells) == 1
    assert engine.sells[0]["tag"] == "newsveto"


def test_tick_skips_when_no_fresh_price(tick_env):
    """해당 보드에 신선한 틱이 없으면(None) 아무것도 하지 않는다 — 15초 경로가 REST 로 본다."""
    engine, state, _ = tick_env

    class Empty:
        def get_fresh(self, stk_cd, prefer_nxt):
            return None

    monitor.check_ticks(engine, state, Empty())
    assert engine.sells == []
