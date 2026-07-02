"""regime_gate 단위 테스트 — 롤링 엣지 게이트의 순수 로직 고정(DB 미접근).

불변식:
  - _score_split: 점수 상위½ 평균수익 − 하위½ 평균수익
  - _split_to_mult: split>=FULL→1.0 / split<=INVERT→MIN_MULT / 사이 선형(단조증가)
  - seed_multiplier: 표본부족→1.0(미개입) / 역전→축소 / 건강→1.0
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


def test_split_to_mult_boundaries():
    assert rg._split_to_mult(rg.REGIME_SPLIT_FULL) == 1.0
    assert rg._split_to_mult(rg.REGIME_SPLIT_FULL + 5) == 1.0
    assert rg._split_to_mult(rg.REGIME_SPLIT_INVERT) == rg.REGIME_MIN_MULT
    assert rg._split_to_mult(rg.REGIME_SPLIT_INVERT - 5) == rg.REGIME_MIN_MULT


def test_split_to_mult_monotonic_midrange():
    lo = rg._split_to_mult(rg.REGIME_SPLIT_INVERT + 0.01)
    mid = rg._split_to_mult((rg.REGIME_SPLIT_FULL + rg.REGIME_SPLIT_INVERT) / 2)
    hi = rg._split_to_mult(rg.REGIME_SPLIT_FULL - 0.01)
    assert rg.REGIME_MIN_MULT <= lo < mid < hi <= 1.0


def test_seed_multiplier_insufficient_samples(monkeypatch):
    monkeypatch.setattr(rg, "_recent_samples", lambda w: [{"score": 1, "next_open_ret": 1.0}])
    mult, diag = rg.seed_multiplier()
    assert mult == 1.0 and diag["gated"] is False and diag["reason"] == "insufficient"


def test_seed_multiplier_inverted_reduces(monkeypatch):
    # 역전(고점수 손실) 표본을 MIN_SAMPLES 이상 → 배수 축소
    bad = [{"score": 90, "next_open_ret": -2.0}, {"score": 10, "next_open_ret": 2.0}]
    monkeypatch.setattr(rg, "_recent_samples", lambda w: bad * rg.REGIME_MIN_SAMPLES)
    mult, diag = rg.seed_multiplier()
    assert diag["gated"] is True and diag["inverted"] is True
    assert mult == rg.REGIME_MIN_MULT


def test_seed_multiplier_healthy_full(monkeypatch):
    good = [{"score": 90, "next_open_ret": 2.0}, {"score": 10, "next_open_ret": -2.0}]
    monkeypatch.setattr(rg, "_recent_samples", lambda w: good * rg.REGIME_MIN_SAMPLES)
    mult, diag = rg.seed_multiplier()
    assert diag["gated"] is True and diag["inverted"] is False
    assert mult == 1.0
