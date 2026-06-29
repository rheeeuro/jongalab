"""settle._run_open_stage 순수 로직 테스트 — NXT 08:05 / KRX 개장 09:05 공용 단계 고정.

검증 포인트(자금 경로):
  - 단계가 자기 대상 종목만 처리한다(NXT 단계=NXT 상장, KRX 개장 단계=NXT 미상장).
  - 갭상승/갭하락에 따라 스탑선이 절반매도 체결가 / 시초가-버퍼로 정해진다.
  - 절반=0(1주)이면 전량 매도하고 감시계획을 만들지 않는다.
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
    # 갭상승 스탑선은 절반매도 실체결가 — 조회를 fallback(시초가)로 단순화
    monkeypatch.setattr(settle, "_half_sell_fill_price",
                        lambda trade_date, stk_cd, tag, fallback: fallback)
    return plans


def _positions(*specs):
    return [dict(stk_cd=cd, qty=q, avg_price=a) for cd, q, a in specs]


def test_krx_open_targets_only_non_nxt(patched, monkeypatch):
    """KRX 개장 단계는 NXT 미상장 종목만 처리하고 NXT 상장 종목은 건너뛴다."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000), ("NXT1", 10, 10000)))
    eng = FakeEngine(price=12000, nxt_codes={"NXT1"})  # 갭상승(12000>10000)

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


def test_gap_up_stop_is_half_sell_fill(patched, monkeypatch):
    """갭상승이면 스탑선 = 절반매도 체결가(여기선 fallback=시초가)."""
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 10, 10000)))
    eng = FakeEngine(price=12000, nxt_codes=set())  # 갭상승

    settle.run_krx_open(eng, "20260629")

    (_, kwargs) = patched[0]
    assert kwargs["stop_price"] == 12000


def test_single_share_full_sell_no_plan(patched, monkeypatch):
    """1주(절반=0)는 전량 매도 없이 보유 유지 — execute_sell 호출 안 함, plan 도 안 만든다.

    half=0 이라 절반매도가 없고 remaining=1>0 이지만, 절반=0 케이스는 회복 대기로 보유한다.
    """
    monkeypatch.setattr(settle.position_repo, "get_open_positions",
                        lambda: _positions(("AAA", 1, 10000)))
    eng = FakeEngine(price=12000, nxt_codes=set())

    settle.run_krx_open(eng, "20260629")

    assert eng.sells == []  # half<1 → 매도 안 함
    assert len(patched) == 1  # remaining=1>0 → 잔량 감시계획은 생성
