"""regime_gate 단위 테스트 — 롤링 엣지 게이트의 순수 로직 고정(DB 미접근).

불변식:
  - _score_split: 점수 상위½ 평균수익 − 하위½ 평균수익
  - _split_to_mult: 이진 — split < INVERT_THRESHOLD → MIN_MULT / 아니면 1.0
  - seed_multiplier: 거래일 부족→1.0(미개입) / 역전→MIN_MULT / 건강→1.0
"""
import core.regime_gate as rg


def test_score_split_positive_when_high_score_wins():
    # 고점수(90,80)가 +2/+1, 저점수(10,20)가 -1/0 → 상위½ 평균 1.5, 하위½ 평균 -0.5 = +2.0
    samples = [
        {"score": 90, "next_open_ret": 2.0},
        {"score": 80, "next_open_ret": 1.0},
        {"score": 20, "next_open_ret": 0.0},
        {"score": 10, "next_open_ret": -1.0},
    ]
    assert rg._score_split(samples) == 2.0


def test_score_split_negative_when_inverted():
    # 고점수가 오히려 손실 → 음수(역전)
    samples = [
        {"score": 90, "next_open_ret": -1.0},
        {"score": 80, "next_open_ret": 0.0},
        {"score": 20, "next_open_ret": 1.0},
        {"score": 10, "next_open_ret": 2.0},
    ]
    assert rg._score_split(samples) == -2.0


def test_split_to_mult_binary():
    # 역전 깊이와 무관하게 이진 — 임계 미만이면 MIN_MULT, 이상이면 1.0
    assert rg._split_to_mult(rg.REGIME_INVERT_THRESHOLD - 0.01) == rg.REGIME_MIN_MULT
    assert rg._split_to_mult(rg.REGIME_INVERT_THRESHOLD - 5) == rg.REGIME_MIN_MULT
    assert rg._split_to_mult(rg.REGIME_INVERT_THRESHOLD) == 1.0
    assert rg._split_to_mult(rg.REGIME_INVERT_THRESHOLD + 5) == 1.0


def test_seed_multiplier_insufficient_days(monkeypatch):
    # 종목-일 표본이 많아도 거래일 수가 부족하면 미개입 — 같은 날 표본은 상관되어 실효 표본이 아니다.
    many = [{"score": 90, "next_open_ret": -2.0}, {"score": 10, "next_open_ret": 2.0}] * 30
    monkeypatch.setattr(rg, "_recent_samples", lambda w: (many, rg.REGIME_MIN_DAYS - 1))
    mult, diag = rg.seed_multiplier()
    assert mult == 1.0 and diag["gated"] is False and diag["reason"] == "insufficient_days"


def test_seed_multiplier_inverted_reduces(monkeypatch):
    # 역전(고점수 손실) + 거래일 충족 → MIN_MULT 로 축소
    bad = [{"score": 90, "next_open_ret": -2.0}, {"score": 10, "next_open_ret": 2.0}] * 20
    monkeypatch.setattr(rg, "_recent_samples", lambda w: (bad, rg.REGIME_MIN_DAYS))
    mult, diag = rg.seed_multiplier()
    assert diag["gated"] is True and diag["inverted"] is True
    assert diag["n_days"] == rg.REGIME_MIN_DAYS
    assert mult == rg.REGIME_MIN_MULT


def test_seed_multiplier_healthy_full(monkeypatch):
    good = [{"score": 90, "next_open_ret": 2.0}, {"score": 10, "next_open_ret": -2.0}] * 20
    monkeypatch.setattr(rg, "_recent_samples", lambda w: (good, rg.REGIME_MIN_DAYS))
    mult, diag = rg.seed_multiplier()
    assert diag["gated"] is True and diag["inverted"] is False
    assert mult == 1.0
