"""jongalab core/edge_predicate.py 최소 복제의 계약 고정 — 드리프트 감지용.

원본을 고치고 이 복제를 안 고치면 **채점(jongalab)과 집행(trading)이 같은 predicate 를
다르게 해석**한다 = "측정한 것과 다른 것을 산다". 아래는 원본 docstring 이 명시한 계약이다.
"""
import pytest

from core.edge_predicate import evaluate, validate_predicate, PredicateError


def test_ops_supported():
    row = {"a": 5, "b": "x", "c": None}
    assert evaluate([{"col": "a", "op": "==", "value": 5}], row)
    assert evaluate([{"col": "a", "op": "!=", "value": 4}], row)
    assert evaluate([{"col": "a", "op": ">", "value": 4}], row)
    assert evaluate([{"col": "a", "op": ">=", "value": 5}], row)
    assert evaluate([{"col": "a", "op": "<", "value": 6}], row)
    assert evaluate([{"col": "a", "op": "<=", "value": 5}], row)
    assert evaluate([{"col": "a", "op": "between", "value": [1, 10]}], row)
    assert evaluate([{"col": "b", "op": "in", "value": ["x", "y"]}], row)
    assert evaluate([{"col": "a", "op": "not_null"}], row)


def test_null_fails_every_op_except_not_null():
    row = {"c": None}
    for op, val in (("==", None), (">", 1), ("between", [0, 1]), ("in", [None])):
        assert evaluate([{"col": "c", "op": op, "value": val}], row) is False
    assert evaluate([{"col": "c", "op": "not_null"}], row) is False   # 값이 None
    assert evaluate([{"col": "missing", "op": "not_null"}], row) is False


def test_and_combination_and_empty_predicate():
    row = {"a": 5, "b": 1}
    assert evaluate([{"col": "a", "op": "==", "value": 5},
                     {"col": "b", "op": "==", "value": 1}], row) is True
    assert evaluate([{"col": "a", "op": "==", "value": 5},
                     {"col": "b", "op": "==", "value": 9}], row) is False
    assert evaluate([], row) is False          # 빈 목록은 매칭 금지(오설정 방어)


def test_market_prefix_reads_market_row():
    assert evaluate([{"col": "market.vix", "op": ">", "value": 20}], {}, {"vix": 25}) is True
    assert evaluate([{"col": "market.vix", "op": ">", "value": 20}], {}, None) is False


def test_bad_op_and_structure_raise():
    with pytest.raises(PredicateError):
        evaluate([{"col": "a", "op": "≈", "value": 1}], {"a": 1})
    with pytest.raises(PredicateError):
        validate_predicate([])
    with pytest.raises(PredicateError):
        validate_predicate([{"col": "a", "op": "between", "value": [1]}])
