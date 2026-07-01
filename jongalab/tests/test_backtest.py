"""가중치 백테스트(core/backtest.py) 테스트.

핵심: recompute_score 가 실제 trading_engine.score_candidate 와 **정확히** 일치하는지 교차검증한다.
엔진(가드 보호 민감 파일) 공식이 바뀌면 이 테스트가 실패해 미러 드리프트를 알린다.
"""
import pytest

from core.backtest import (
    recompute_score, evaluate_weights, backtest_proposal, _ranks, _spearman,
)
from core.trading_engine import AnalysisEngine, StockCandidate, StrategyConfig
from workers.closing_bet import ClosingBetStrategy


# recompute_score 가 사용하는 가중치/임계값 키 (StrategyConfig 인스턴스에서 추출)
_W_KEYS = [
    "SCORE_SUPPLY_BONUS", "SCORE_MA_ALIGNED_BONUS", "SCORE_NEAR_HIGH_BONUS",
    "PREFERRED_TRADING_VALUE", "MIN_TRADING_VALUE",
    "SCORE_PREFERRED_VALUE_BONUS", "SCORE_MIN_VALUE_BONUS",
    "SCORE_LEADER_BONUS", "SCORE_PROGRAM_BUY_BONUS", "THEME_STOCK_BONUS",
    "SCORE_EXTRA_SUPPLY_DAY_BONUS", "CONTENT_SCORE_MAX",
    "SCORE_NEWS_BONUS", "NEWS_HEAT_CAP",
]


def _weights(cfg) -> dict:
    return {k: getattr(cfg, k) for k in _W_KEYS}


def _row(c: StockCandidate) -> dict:
    """StockCandidate → 저장된 daily_stock_report 행과 동일한 dict (content_score 는 실제 계산 재사용)."""
    return {
        "stk_cd": c.code, "name": c.name,
        "supply_score": c.supply_score,
        "ma_aligned": c.ma_aligned, "near_high": c.near_high,
        "trading_value": c.trading_value,
        "is_leader": c.is_leader, "prog_net_buy": c.prog_net_buy,
        "is_theme_stock": c.is_theme_stock, "supply_days": c.supply_days,
        "content_score": ClosingBetStrategy._calc_content_score(c),
        "news_count": c.news_count,
    }


# 다양한 조합의 후보 (브래킷·플래그·콘텐츠·연속일 경계 포함)
_CANDIDATES = [
    StockCandidate(code="A", name="a", sector="s"),  # 전부 기본(0/False)
    StockCandidate(code="B", name="b", sector="s", supply_score=100, ma_aligned=True,
                   near_high=True, trading_value=250_000_000_000, is_leader=True,
                   prog_net_buy=500, is_theme_stock=True, supply_days=12,
                   content_count=3, content_avg_score=80, news_count=7),
    StockCandidate(code="C", name="c", sector="s", supply_score=55,
                   trading_value=150_000_000_000, supply_days=7,
                   content_count=1, content_avg_score=55),
    StockCandidate(code="D", name="d", sector="s", supply_score=30, ma_aligned=True,
                   trading_value=99_000_000_000, prog_net_buy=-10,
                   content_count=2, content_avg_score=40),
]


@pytest.mark.parametrize("c", _CANDIDATES, ids=lambda c: c.code)
def test_recompute_matches_engine_default_weights(c):
    cfg = StrategyConfig()
    real = AnalysisEngine(api=None, config=cfg).score_candidate(c)
    mine = recompute_score(_row(c), _weights(cfg))
    assert mine == real


@pytest.mark.parametrize("c", _CANDIDATES, ids=lambda c: c.code)
def test_recompute_matches_engine_tuned_weights(c):
    # 가중치를 비기본값으로 바꿔도 미러가 엔진과 일치하는지(가중치 적용 경로 검증)
    cfg = StrategyConfig()
    cfg.SCORE_SUPPLY_BONUS = 60.0
    cfg.THEME_STOCK_BONUS = 5
    cfg.SCORE_LEADER_BONUS = 20
    cfg.CONTENT_SCORE_MAX = 4          # 콘텐츠 상한 < 10 → 재캡 경로 검증
    cfg.SCORE_PROGRAM_BUY_BONUS = 0
    cfg.SCORE_NEWS_BONUS = 8           # 뉴스 가중치 상향 → 뉴스 가점 경로 검증
    real = AnalysisEngine(api=None, config=cfg).score_candidate(c)
    mine = recompute_score(_row(c), _weights(cfg))
    assert mine == real


def test_recompute_uses_defaults_for_missing_keys():
    # weights 에 없는 키는 전략 기본값으로 폴백 → 빈 dict 도 기본 엔진과 동일
    c = _CANDIDATES[1]
    real = AnalysisEngine(api=None, config=StrategyConfig()).score_candidate(c)
    assert recompute_score(_row(c), {}) == real


# ── 순위/상관 유틸 ──

def test_ranks_with_ties_uses_average():
    assert _ranks([10, 20, 20, 40]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_perfect_positive():
    assert _spearman([(1, 10), (2, 20), (3, 30)]) == 1.0


def test_spearman_perfect_negative():
    assert _spearman([(1, 30), (2, 20), (3, 10)]) == -1.0


def test_spearman_none_when_degenerate():
    assert _spearman([(5, 5)]) is None          # n<2
    assert _spearman([(5, 1), (5, 2)]) is None   # x 전부 동점


# ── 집계/판정 ──

def _sample(stk, pnl, **kw):
    base = dict(stk_cd=stk, name=stk, realized_pnl=pnl,
                outcome="WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT",
                supply_score=50, ma_aligned=False, near_high=False, trading_value=0,
                is_leader=False, prog_net_buy=0, is_theme_stock=False,
                supply_days=0, content_score=0)
    base.update(kw)
    return base


def test_evaluate_weights_spread_and_scores():
    samples = [_sample("W", 100, is_theme_stock=True), _sample("L", -100)]
    m = evaluate_weights(samples, {})
    assert m["winner_avg_score"] is not None and m["loser_avg_score"] is not None
    assert m["spread"] == round(m["winner_avg_score"] - m["loser_avg_score"], 1)
    assert len(m["scores"]) == 2


def test_backtest_verdict_improves_when_spread_widens():
    # 승자만 테마주 → 테마 가중치를 올리면 승자-패자 점수차가 벌어진다 = 개선
    samples = [_sample("W", 100, is_theme_stock=True), _sample("L", -100, is_theme_stock=False)]
    out = backtest_proposal(samples, {"THEME_STOCK_BONUS": 0}, {"THEME_STOCK_BONUS": 30})
    assert out["verdict"] == "IMPROVES"
    assert out["spread_delta"] > 0


def test_backtest_verdict_worsens_when_spread_narrows():
    # 패자만 테마주 → 테마 가중치를 올리면 패자가 더 높아져 판별력 악화
    samples = [_sample("W", 100, is_theme_stock=False), _sample("L", -100, is_theme_stock=True)]
    out = backtest_proposal(samples, {"THEME_STOCK_BONUS": 0}, {"THEME_STOCK_BONUS": 30})
    assert out["verdict"] == "WORSENS"
    assert out["spread_delta"] < 0


def test_backtest_insufficient_without_both_outcomes():
    samples = [_sample("W1", 100), _sample("W2", 50)]   # 승자뿐
    out = backtest_proposal(samples, {}, {"THEME_STOCK_BONUS": 30})
    assert out["verdict"] == "INSUFFICIENT"
    assert out["current"]["spread"] is None
