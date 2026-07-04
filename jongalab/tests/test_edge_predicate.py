"""Predicate DSL 평가기(core/edge_predicate.py) 단위 테스트.

DB·네트워크 무의존 순수 로직이라 계약을 여기서 고정한다:
op 7종 × 정상/경계/NULL, market.* 참조, AND 결합, 미지원 op·구조 오류, validate_predicate.
"""
import pytest

from core.edge_predicate import evaluate, validate_predicate, PredicateError


ROW = {
    "nxt_gap_pct": 2.5,
    "sector_rel_ret": 0.0,
    "news_first_today": 1,
    "is_leader": 0,
    "news_catalyst": "실적",
    "next_low_ret": None,
    "stock_code": "005930",
}
MARKET = {"nq_fut_ret": -0.1, "vix": 16.2}


# ── op 별 정상 ──
def test_eq():
    assert evaluate([{"col": "news_first_today", "op": "==", "value": 1}], ROW) is True
    assert evaluate([{"col": "news_first_today", "op": "==", "value": 0}], ROW) is False


def test_ne():
    assert evaluate([{"col": "is_leader", "op": "!=", "value": 1}], ROW) is True


def test_gte_lte():
    assert evaluate([{"col": "nxt_gap_pct", "op": ">=", "value": 2.5}], ROW) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": "<=", "value": 2.5}], ROW) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": ">=", "value": 2.6}], ROW) is False


def test_gt_lt_strict():
    # 경계에서 strict(>,<)와 non-strict(>=,<=) 가 갈린다 — f3_nxt_gap_thin 의 sector_rel_ret<0 근거
    assert evaluate([{"col": "sector_rel_ret", "op": "<", "value": 0}], ROW) is False  # 0 은 <0 아님
    assert evaluate([{"col": "sector_rel_ret", "op": ">", "value": 0}], ROW) is False  # 0 은 >0 아님
    neg = ROW | {"sector_rel_ret": -0.5}
    assert evaluate([{"col": "sector_rel_ret", "op": "<", "value": 0}], neg) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": ">", "value": 2.4}], ROW) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": ">", "value": 2.5}], ROW) is False


def test_between_inclusive_bounds():
    assert evaluate([{"col": "nxt_gap_pct", "op": "between", "value": [1.0, 6.0]}], ROW) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": "between", "value": [2.5, 2.5]}], ROW) is True
    assert evaluate([{"col": "nxt_gap_pct", "op": "between", "value": [3.0, 6.0]}], ROW) is False


def test_in():
    assert evaluate([{"col": "news_catalyst", "op": "in", "value": ["실적", "수주계약"]}], ROW) is True
    assert evaluate([{"col": "news_catalyst", "op": "in", "value": ["M&A"]}], ROW) is False


def test_not_null():
    assert evaluate([{"col": "nxt_gap_pct", "op": "not_null"}], ROW) is True
    assert evaluate([{"col": "next_low_ret", "op": "not_null"}], ROW) is False
    assert evaluate([{"col": "absent_col", "op": "not_null"}], ROW) is False


# ── NULL 처리 (not_null 외 전부 매칭 실패) ──
def test_null_fails_all_non_notnull_ops():
    for op, value in [(">=", 0), ("<=", 0), ("==", 5), ("!=", 5),
                      ("between", [0, 1]), ("in", [1, 2])]:
        cond = {"col": "next_low_ret", "op": op, "value": value}
        assert evaluate([cond], ROW) is False, op
    # 부재 컬럼도 동일
    assert evaluate([{"col": "absent", "op": ">=", "value": 0}], ROW) is False


# ── market.* 참조 ──
def test_market_reference():
    assert evaluate([{"col": "market.nq_fut_ret", "op": ">=", "value": -0.3}], ROW, MARKET) is True
    assert evaluate([{"col": "market.nq_fut_ret", "op": ">=", "value": 0}], ROW, MARKET) is False
    # market 미제공(None) → 값 없음 → 매칭 실패
    assert evaluate([{"col": "market.nq_fut_ret", "op": ">=", "value": -0.3}], ROW, None) is False


# ── AND 결합 ──
def test_and_combination():
    pred = [
        {"col": "nxt_gap_pct", "op": "between", "value": [1.0, 6.0]},
        {"col": "sector_rel_ret", "op": ">=", "value": 0},
        {"col": "market.nq_fut_ret", "op": ">=", "value": -0.3},
    ]
    assert evaluate(pred, ROW, MARKET) is True
    # 한 조건만 깨져도 전체 False
    bad = ROW | {"sector_rel_ret": -1.0}
    assert evaluate(pred, bad, MARKET) is False


def test_empty_predicate_is_false():
    """빈 predicate 는 오설정 방어로 False(무조건 매칭 금지)."""
    assert evaluate([], ROW) is False


# ── 오류 ──
def test_unsupported_op_raises():
    with pytest.raises(PredicateError):
        evaluate([{"col": "nxt_gap_pct", "op": "~=", "value": 1}], ROW)


def test_bad_between_value_raises():
    with pytest.raises(PredicateError):
        evaluate([{"col": "nxt_gap_pct", "op": "between", "value": [1.0]}], ROW)


def test_non_numeric_comparison_raises():
    with pytest.raises(PredicateError):
        evaluate([{"col": "news_catalyst", "op": ">=", "value": 3}], ROW)


def test_predicate_not_list_raises():
    with pytest.raises(PredicateError):
        evaluate({"col": "x", "op": "==", "value": 1}, ROW)


# ── validate_predicate ──
def test_validate_ok():
    validate_predicate([
        {"col": "nxt_gap_pct", "op": "between", "value": [1, 6]},
        {"col": "nxt_price_1950", "op": "not_null"},
    ])


def test_validate_rejects_empty():
    with pytest.raises(PredicateError):
        validate_predicate([])


def test_validate_rejects_missing_value():
    with pytest.raises(PredicateError):
        validate_predicate([{"col": "nxt_gap_pct", "op": ">="}])


def test_validate_rejects_bad_op_and_between_and_in():
    with pytest.raises(PredicateError):
        validate_predicate([{"col": "x", "op": "LIKE", "value": 1}])
    with pytest.raises(PredicateError):
        validate_predicate([{"col": "x", "op": "between", "value": 5}])
    with pytest.raises(PredicateError):
        validate_predicate([{"col": "x", "op": "in", "value": 5}])
