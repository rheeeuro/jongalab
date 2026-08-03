"""NXT 야간 갭 계산 순수 로직 고정 (DB·네트워크 미접근).

집행기가 19:50 주문 직전에 채우는 값의 정의만 여기서 고정한다. **밴드·조건 판정은
`core/edge_execution` + 원장 rule 의 predicate 소관**이라 `tests/test_edge_execution.py` 에 있다
(2026-08-03 하드코딩 상수 → 원장 predicate 로 이관하면서 분리).

불변식:
  - 갭 = (NXT 현재가 − KRX 확정 종가) / KRX 확정 종가 × 100.
    채점 쪽 `gap_check --base-nxt`(19:50)가 같은 식으로 `nxt_gap_pct` 를 기록한다 — 두 정의가
    어긋나면 "측정한 것과 다른 것을 산다"가 되므로 이 식이 계약이다.
  - 재료가 없으면(가격 0/음수) None → 호출부가 fail-open(매수)으로 폴백한다.
"""
import workers.signal_executor as se


def test_gap_is_percent_change_from_krx_close():
    assert se._nxt_gap_pct(10_300, 10_000) == 3.0
    assert se._nxt_gap_pct(9_700, 10_000) == -3.0
    assert se._nxt_gap_pct(10_000, 10_000) == 0.0


def test_missing_inputs_return_none_for_fail_open():
    assert se._nxt_gap_pct(0, 10_000) is None
    assert se._nxt_gap_pct(10_300, 0) is None
    assert se._nxt_gap_pct(-1, 10_000) is None
    assert se._nxt_gap_pct(10_300, -1) is None


def test_real_measured_values_reproduce():
    """2026-08-03 실집행 audit 값 재현(회귀 고정)."""
    assert round(se._nxt_gap_pct(105_800, 108_700), 3) == -2.668   # 에스피지
    assert round(se._nxt_gap_pct(384_000, 393_000), 3) == -2.290   # 현대차
    assert round(se._nxt_gap_pct(84_200, 87_500), 3) == -3.771     # 심텍
