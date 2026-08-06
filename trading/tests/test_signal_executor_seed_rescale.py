"""데드라인 직전 SEED_INIT_MULT 재조회(_rescale_by_seed_mult) 테스트.

수량은 윈도우 시작에 확정되지만, 사람이 그 뒤 대시보드에서 시드를 줄이면 데드라인 직전에
그 비율만큼 축소돼야 한다(축소 전용). 올라갔거나 조회가 실패하면 확정 수량 그대로다.
"""
import pytest

from workers import signal_executor as se


class Recorder:
    def __init__(self):
        self.events = []   # (event, stk_cd, payload)
        self.status = []   # (signal_id, status, note)

    @property
    def event_types(self):
        return [e[0] for e in self.events]


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    monkeypatch.setattr(se.audit_log, "append",
                        lambda event, stk_cd, payload: r.events.append((event, stk_cd, payload)))
    monkeypatch.setattr(se.signal_repo, "update_status",
                        lambda sid, status, note=None: r.status.append((sid, status, note)))
    return r


def _set_mult(monkeypatch, value):
    monkeypatch.setattr(se.risk_config_repo, "get_risk_config",
                        lambda: {"SEED_INIT_MULT": value})


def _cand(stk_cd, shares, price=10000, sig_id=1, bought=False):
    return {"sig": {"id": sig_id}, "stk_cd": stk_cd, "price": price,
            "shares": shares, "cost": shares * price, "bought": bought}


def test_reduced_mult_scales_shares_down(monkeypatch, rec):
    """0.75 → 0.4 로 낮추면 비율(0.533)만큼 반올림 축소된다."""
    _set_mult(monkeypatch, 0.4)
    cands = [_cand("000100", 20), _cand("000200", 3, sig_id=2)]

    se._rescale_by_seed_mult(cands, 0.75, "nxt")

    assert cands[0]["shares"] == 11        # 20 × 0.5333 = 10.67 → 반올림 11
    assert cands[0]["cost"] == 11 * 10000  # cost 도 함께 갱신
    assert cands[1]["shares"] == 2         # 3 × 0.5333 = 1.6 → 2
    assert "seed_init_rescale" in rec.event_types
    payload = next(p for e, _, p in rec.events if e == "seed_init_rescale")
    assert payload["applied_mult"] == 0.75 and payload["deadline_mult"] == 0.4
    assert payload["stocks"]["000100"] == {"before": 20, "after": 11}


def test_unchanged_or_raised_mult_is_noop(monkeypatch, rec):
    """같거나 올라간 값은 무개입 — 증액은 주문가능금액 초과를 부른다(reduce-only)."""
    for now_mult in (0.75, 1.0):
        _set_mult(monkeypatch, now_mult)
        cands = [_cand("000100", 20)]
        se._rescale_by_seed_mult(cands, 0.75, "nxt")
        assert cands[0]["shares"] == 20
    assert rec.events == []


def test_zero_shares_after_cut_is_skipped(monkeypatch, rec):
    """절반 넘게 깎여 0주가 되면 매수하지 않고 시그널을 skipped 로 마감한다."""
    _set_mult(monkeypatch, 0.1)
    cands = [_cand("000100", 1, sig_id=7)]

    se._rescale_by_seed_mult(cands, 1.0, "krx")

    assert cands[0]["shares"] == 0
    assert cands[0]["bought"] is True      # 데드라인 루프 대상에서 제외
    assert rec.status == [(7, "skipped", "시드 축소 0주")]
    assert "buy_skip" in rec.event_types


def test_already_bought_or_zero_untouched(monkeypatch, rec):
    """이미 집행·스킵된 후보(bought)는 건드리지 않는다."""
    _set_mult(monkeypatch, 0.5)
    cands = [_cand("000100", 20, bought=True), _cand("000200", 0, sig_id=2, bought=True)]

    se._rescale_by_seed_mult(cands, 1.0, "nxt")

    assert cands[0]["shares"] == 20 and cands[1]["shares"] == 0
    assert rec.status == []


def test_config_read_failure_is_fail_open(monkeypatch, rec):
    """재조회 실패는 확정 수량 유지 — 매수를 막지 않는다."""
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(se.risk_config_repo, "get_risk_config", _boom)
    cands = [_cand("000100", 20)]

    se._rescale_by_seed_mult(cands, 1.0, "nxt")

    assert cands[0]["shares"] == 20
    assert rec.events == []


def test_zero_applied_mult_is_noop(monkeypatch, rec):
    """적용 배율이 0이면 비율 계산이 불가 — 무개입(0으로 나누지 않는다)."""
    _set_mult(monkeypatch, 0.5)
    cands = [_cand("000100", 20)]

    se._rescale_by_seed_mult(cands, 0.0, "nxt")

    assert cands[0]["shares"] == 20
    assert rec.events == []
