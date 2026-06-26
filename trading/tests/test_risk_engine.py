"""RiskEngine.check 게이트키핑 테스트 — 자금 손실 직결 분기 고정.

검사 순서(불변): 킬스위치 → 종목당 명목 → 일일 손실(초과 시 서킷브레이커) →
일일 주문수 → 동시 보유 종목수(신규 종목만).
DB 는 monkeypatch 로 대체한다(실제 연결 없음). cfg 를 명시 주입해 load_from_db 우회.
"""
import pytest

from core import risk_engine as re
from core.risk_engine import RiskEngine, RiskConfig


@pytest.fixture
def patched(monkeypatch):
    """기본 '통과' 상태로 모든 DB 의존을 막아두고, 테스트가 개별 항목만 흔든다."""
    monkeypatch.setattr(re, "TRADING_KILL_SWITCH", False)
    monkeypatch.setattr(re.risk_repo, "get_kill_switch", lambda: False)
    monkeypatch.setattr(re.risk_repo, "get_state", lambda d: {})
    monkeypatch.setattr(re.position_repo, "get_open_positions", lambda: [])
    # 서킷브레이커 부수효과 기록
    tripped = {"kill": [], "breaker": []}
    monkeypatch.setattr(re.risk_repo, "set_kill_switch",
                        lambda flag, reason: tripped["kill"].append((flag, reason)))
    monkeypatch.setattr(re.risk_repo, "set_breaker",
                        lambda d, flag: tripped["breaker"].append((d, flag)))
    return monkeypatch, tripped


def _engine():
    # cfg 명시 주입 → 생성자가 DB(load_from_db)를 부르지 않는다(기본 한도 사용).
    return RiskEngine(cfg=RiskConfig())


def test_allows_clean_order(patched):
    eng = _engine()
    d = eng.check("20260626", "005930", 1_000_000)
    assert d.allowed is True


def test_env_kill_switch_blocks(patched):
    mp, _ = patched
    mp.setattr(re, "TRADING_KILL_SWITCH", True)
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False and "kill_switch" in d.reason


def test_db_kill_switch_blocks(patched):
    mp, _ = patched
    mp.setattr(re.risk_repo, "get_kill_switch", lambda: True)
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False and "kill_switch" in d.reason


def test_kill_switch_fails_safe_on_db_error(patched):
    # 리스크 상태를 못 읽으면 안전상 차단(True) 쪽으로 판단해야 한다
    mp, _ = patched

    def boom():
        raise RuntimeError("db down")

    mp.setattr(re.risk_repo, "get_kill_switch", boom)
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False


def test_per_name_notional_cap_blocks(patched):
    # 기본 종목당 한도 5,000,000 초과
    d = _engine().check("20260626", "005930", 5_000_001)
    assert d.allowed is False and "종목당" in d.reason


def test_daily_loss_trips_circuit_breaker(patched):
    mp, tripped = patched
    mp.setattr(re.risk_repo, "get_state", lambda d: {"realized_pnl": -3_000_000})
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False
    assert "서킷브레이커" in d.reason
    assert tripped["kill"] and tripped["kill"][0][0] is True   # 킬스위치 ON
    assert tripped["breaker"] and tripped["breaker"][0][1] is True


def test_daily_order_count_limit_blocks(patched):
    mp, _ = patched
    mp.setattr(re.risk_repo, "get_state", lambda d: {"orders_count": 10})  # 기본 한도 10
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False and "주문수" in d.reason


def test_max_positions_blocks_new_ticker(patched):
    mp, _ = patched
    held = [{"stk_cd": f"{i:06d}"} for i in range(5)]   # 기본 한도 5 종목 보유
    mp.setattr(re.position_repo, "get_open_positions", lambda: held)
    d = _engine().check("20260626", "999999", 1_000_000)  # 신규 종목
    assert d.allowed is False and "보유 종목수" in d.reason


def test_max_positions_allows_existing_ticker(patched):
    mp, _ = patched
    held = [{"stk_cd": f"{i:06d}"} for i in range(5)]
    mp.setattr(re.position_repo, "get_open_positions", lambda: held)
    # 이미 보유 중인 종목 추가매수는 종목수 한도에서 제외 → 허용
    d = _engine().check("20260626", "000000", 1_000_000)
    assert d.allowed is True


def test_position_read_failure_fails_safe(patched):
    mp, _ = patched

    def boom():
        raise RuntimeError("db down")

    mp.setattr(re.position_repo, "get_open_positions", boom)
    d = _engine().check("20260626", "005930", 1_000_000)
    assert d.allowed is False
