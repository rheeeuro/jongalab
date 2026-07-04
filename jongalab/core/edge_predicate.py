"""Predicate DSL 평가기 — 순수 함수(DB·네트워크 무의존).

edge_rule.predicate 는 조건 목록의 **AND 결합**이다. OR·중첩은 지원하지 않는다
(OR 가 필요하면 rule 을 쪼갠다 — 가설은 원자적이어야 손익 귀속이 된다).
교차 행 계산이 필요한 조건은 스냅샷 시점에 파생 컬럼으로 구워 predicate 를 행 단위로 유지한다.

각 조건: {"col": <컬럼>, "op": <연산자>, "value": <값>}
  - col 에 "market." 접두사 → market(=market_snapshot 행)의 컬럼 참조(F2 해외 동조용).
    그 외는 종목 행(daily_stock_report row) 참조.
  - op: == != > >= < <= between in not_null (9종)
  - NULL 처리: 대상 컬럼이 NULL/부재면 not_null 을 제외한 모든 op 에서 **매칭 실패**로 처리한다
    (보수적 — NULL 을 통과시키면 결측이 많은 날 rule 이 오염된다).

DB·네트워크 무의존이므로 tests/test_edge_predicate.py 단위 테스트로 계약을 고정한다.
"""

_OPS = {"==", "!=", ">", ">=", "<", "<=", "between", "in", "not_null"}
_MARKET_PREFIX = "market."


class PredicateError(ValueError):
    """predicate 구조/연산자 오류 — 저장 전 검증과 평가 양쪽에서 던진다."""


def _num(v):
    """수치 비교용 float 변환. bool 은 0/1, 변환 불가는 PredicateError."""
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise PredicateError(f"수치 비교 불가 값: {v!r}")


def _resolve(col: str, row: dict, market: dict | None):
    """col 값 해석. 'market.' 접두사면 market 행에서, 아니면 종목 행에서 조회."""
    if col.startswith(_MARKET_PREFIX):
        return (market or {}).get(col[len(_MARKET_PREFIX):])
    return (row or {}).get(col)


def _match_one(cond: dict, row: dict, market: dict | None) -> bool:
    if not isinstance(cond, dict):
        raise PredicateError(f"조건은 객체여야 합니다: {cond!r}")
    col = cond.get("col")
    op = cond.get("op")
    if not isinstance(col, str) or not col:
        raise PredicateError(f"조건에 col 이 없습니다: {cond!r}")
    if op not in _OPS:
        raise PredicateError(f"지원하지 않는 op: {op!r} (지원: {sorted(_OPS)})")

    val = _resolve(col, row, market)

    if op == "not_null":
        return val is not None
    if val is None:
        return False  # NULL 은 not_null 외 모든 op 에서 매칭 실패(보수적)

    target = cond.get("value")
    if op == "==":
        return val == target
    if op == "!=":
        return val != target
    if op == ">":
        return _num(val) > _num(target)
    if op == ">=":
        return _num(val) >= _num(target)
    if op == "<":
        return _num(val) < _num(target)
    if op == "<=":
        return _num(val) <= _num(target)
    if op == "between":
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            raise PredicateError(f"between value 는 [lo, hi] 여야 합니다: {target!r}")
        return _num(target[0]) <= _num(val) <= _num(target[1])
    if op == "in":
        if not isinstance(target, (list, tuple)):
            raise PredicateError(f"in value 는 리스트여야 합니다: {target!r}")
        return val in target
    raise PredicateError(f"미처리 op: {op}")  # 도달 불가(위에서 _OPS 검증)


def evaluate(predicate: list, row: dict, market: dict | None = None) -> bool:
    """predicate(조건 목록)의 AND 결합 평가. 빈 목록은 False(무조건 매칭 금지 — 오설정 방어).

    row: daily_stock_report 한 행(dict). market: 해당 report_date 의 market_snapshot 행(dict|None).
    """
    if not isinstance(predicate, list):
        raise PredicateError("predicate 는 조건 리스트여야 합니다")
    if not predicate:
        return False
    return all(_match_one(c, row, market) for c in predicate)


def validate_predicate(predicate) -> None:
    """저장 전 구조 검증 — 문제가 있으면 PredicateError. 값 유무·형태까지 점검한다."""
    if not isinstance(predicate, list) or not predicate:
        raise PredicateError("predicate 는 비어있지 않은 조건 리스트여야 합니다")
    for c in predicate:
        if not isinstance(c, dict):
            raise PredicateError(f"조건은 객체여야 합니다: {c!r}")
        col = c.get("col")
        op = c.get("op")
        if not isinstance(col, str) or not col:
            raise PredicateError(f"조건에 col(문자열)이 필요합니다: {c!r}")
        if op not in _OPS:
            raise PredicateError(f"지원하지 않는 op: {op!r} (지원: {sorted(_OPS)})")
        if op == "not_null":
            continue
        if "value" not in c:
            raise PredicateError(f"op={op} 에는 value 가 필요합니다: {c!r}")
        target = c.get("value")
        if op == "between" and (not isinstance(target, (list, tuple)) or len(target) != 2):
            raise PredicateError(f"between value 는 [lo, hi] 여야 합니다: {c!r}")
        if op == "in" and not isinstance(target, (list, tuple)):
            raise PredicateError(f"in value 는 리스트여야 합니다: {c!r}")
