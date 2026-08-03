"""settle._run_open_stage 순수 로직 테스트 — NXT 08:03 / KRX 개장 09:03 공용 단계 고정.

검증 포인트(자금 경로):
  - 단계가 자기 대상 종목만 처리한다(NXT 단계=NXT 상장, KRX 개장 단계=NXT 미상장).
  - **갭상승은 전량 매도하고 감시계획을 만들지 않는다**(2026-08-03 잔량 트레일링 폐지).
  - 갭하락은 절반 매도 + 스탑선 = 시초가-버퍼로 잔량 감시계획을 만든다.
  - 갭하락 1주(절반=0)는 매도 없이 감시계획만 만든다(회복 대기).
DB·네트워크 없이 fake 로 검증한다(conftest 철학 동일).
"""
import pytest

from workers import settle
from core.config import STOP_BUFFER_PCT


class FakeData:
    def __init__(self, price, nxt_codes):
        self._price = price
        self._nxt = set(nxt_codes)

    def get_market_price(self, stk_cd):
        return self._price

    def is_nxt_enabled(self, stk_cd):
        return stk_cd in self._nxt


class FakeEngine:
    def __init__(self, price, nxt_codes):
        self.client = object()
        self.data = FakeData(price, nxt_codes)
        self.sells = []

    def execute_sell(self, trade_date, stk_cd, qty, price, dmst_stex_tp=None, tag=None):
        self.sells.append(dict(stk_cd=stk_cd, qty=qty, price=price, stex=dmst_stex_tp, tag=tag))
        return True


@pytest.fixture
def patched(monkeypatch):
    """upsert_plan/sync_fills 을 fake 로 교체하고, 생성된 plan 을 수집한다."""
    plans = []
    monkeypatch.setattr(settle, "sync_fills", lambda client: None)
    monkeypatch.setattr(settle.plan_repo, "upsert_plan",
                        lambda *a, **k: plans.append((a, k)))
    return plans


def _positions(*specs):
    return [dict(stk_cd=cd, qty=q, avg_price=a) for cd, q, a in specs]


def test_krx_open_targets_only_non_nxt(patched, monkeypatch):
    """KRX 개장 단계는 NXT 미상장 종목만 처리하고 NXT 상장 종목은 건너뛴다."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000), ("NXT1", 10, 10000)))
    eng = FakeEngine(price=9000, nxt_codes={"NXT1"})  # 갭하락 — 절반매도 경로

    settle.run_krx_open(eng, "20260629")

    assert [s["stk_cd"] for s in eng.sells] == ["AAA"], "비-NXT 만 매도해야 한다"
    assert eng.sells[0]["stex"] == "KRX" and eng.sells[0]["tag"] == "krxopen"
    assert eng.sells[0]["qty"] == 5  # 절반(10//2)
    assert len(patched) == 1  # 잔량 plan 1건


def test_nxt_targets_only_nxt(patched, monkeypatch):
    """NXT 단계는 NXT 상장 종목만 처리한다(거울 단계)."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000), ("NXT1", 10, 10000)))
    eng = FakeEngine(price=12000, nxt_codes={"NXT1"})

    settle.run_nxt(eng, "20260629")

    assert [s["stk_cd"] for s in eng.sells] == ["NXT1"]
    assert eng.sells[0]["stex"] == "NXT" and eng.sells[0]["tag"] == "nxt"


def test_gap_down_stop_is_open_minus_buffer(patched, monkeypatch):
    """갭하락이면 스탑선 = 시초가*(1-STOP_BUFFER_PCT%)."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000)))
    eng = FakeEngine(price=9000, nxt_codes=set())  # 갭하락(9000<10000)

    settle.run_krx_open(eng, "20260629")

    (_, kwargs) = patched[0]
    assert kwargs["stop_price"] == round(9000 * (1 - STOP_BUFFER_PCT / 100))


def test_gap_up_sells_full_qty_without_plan(patched, monkeypatch):
    """갭상승이면 잔량 없이 전량 매도하고 감시계획을 만들지 않는다(2026-08-03 변경).

    종전엔 절반만 팔고 잔량 스탑선을 절반매도 체결가(버퍼 0)로 뒀으나, 실체결 66건에서
    잔량이 65/66건 더 싸게 팔려(중앙 보유 0분) 잔량 경로 자체를 없앴다.
    """
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000)))
    eng = FakeEngine(price=12000, nxt_codes=set())  # 갭상승

    settle.run_krx_open(eng, "20260629")

    assert len(eng.sells) == 1
    assert eng.sells[0]["qty"] == 10  # 절반(5)이 아니라 전량
    assert eng.sells[0]["price"] == 12000 and eng.sells[0]["tag"] == "krxopen"
    assert patched == [], "갭상승은 감시계획을 만들지 않는다"


def test_gap_up_single_share_sells_full(patched, monkeypatch):
    """갭상승 1주도 전량(1주) 매도 — 종전엔 절반=0 이라 매도 없이 plan 만 만들었다."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 1, 10000)))
    eng = FakeEngine(price=12000, nxt_codes=set())

    settle.run_krx_open(eng, "20260629")

    assert [s["qty"] for s in eng.sells] == [1]
    assert patched == []


def test_gap_down_single_share_holds_with_plan(patched, monkeypatch):
    """갭하락 1주(절반=0)는 매도 없이 감시계획만 — 회복 대기(무변경)."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 1, 10000)))
    eng = FakeEngine(price=9000, nxt_codes=set())

    settle.run_krx_open(eng, "20260629")

    assert eng.sells == []  # half<1 → 매도 안 함
    assert len(patched) == 1  # remaining=1>0 → 잔량 감시계획은 생성
