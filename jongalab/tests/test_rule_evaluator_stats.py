"""workers/rule_evaluator._recompute_stats 계약 고정 — 순수 집계(DB·네트워크 무의존).

게이트가 쓰는 원시 계열(mean_net·ci_low·t_days)과, **룰 상세 화면 표기 전용**인 유니버스
자기제외 초과 계열(mean_exc·ci_low_exc·t_days_exc, 2026-07-28 도입 / 2026-08-04 게이트에서
제외)을 함께 고정한다. 초과 계열은 이제 판정에 쓰지 않지만 "장 덕에 올랐나"를 사람이 보는
값이라 정확해야 한다 — 자기제외를 빼먹으면 rule 이 자기 자신을 기준선에 넣어 초과분이 0 쪽으로
눌리는데(대조군 기준 시 겹침 평균 54%·일부 100%), 그게 이 테스트의 핵심 표적이다.
"""
from core.config import EDGE_COST_PCT
from workers.rule_evaluator import _recompute_stats, _slice_sample_days


def _day(d, matched):
    return {"report_date": d, "matched": matched}


def _m(code, ret, low=None):
    return {"code": code, "name": code, "ret": ret, "low": low}


# ── 원시 계열 ──

def test_raw_series_subtracts_cost_and_counts_days():
    rows = [_day("2026-07-01", [_m("A", 1.0), _m("B", 3.0)]),
            _day("2026-07-02", [_m("A", -1.0)])]
    s = _recompute_stats(rows)
    assert s["n"] == 3 and s["n_days"] == 2
    # 종목-일 가중 평균 = (1+3-1)/3 - 비용
    assert s["mean_net"] == round(1.0 - EDGE_COST_PCT, 3)
    # 일 등가중 평균 = ((1+3)/2 + (-1))/2 - 비용 → 종목-일 가중과 다르다
    assert s["mean_net_days"] == round(0.5 - EDGE_COST_PCT, 3)


def test_empty_returns_none_shape_including_excess_keys():
    s = _recompute_stats([_day("2026-07-01", [])])
    assert s["n"] == 0 and s["n_exc"] == 0
    for k in ("mean_net", "ci_low", "t_days", "mean_exc", "ci_low_exc", "t_days_exc"):
        assert s[k] is None


# ── 초과 계열: 유니버스 자기제외 ──

def test_excess_baseline_excludes_the_rules_own_stocks():
    # 유니버스 4종목 합 8.0 (A=5, 나머지 3종목 합 3.0 → 자기제외 평균 1.0).
    # A 만 매칭 → 초과 = 5.0 - 1.0 = 4.0.
    # 자기제외를 안 하면 기준선이 8/4=2.0 이 되어 초과가 3.0 으로 눌린다.
    rows = [_day("2026-07-01", [_m("A", 5.0)])]
    s = _recompute_stats(rows, {"2026-07-01": (8.0, 4)})
    assert s["n_exc"] == 1
    assert s["mean_exc"] == 4.0


def test_excess_ignores_cost_because_it_cancels():
    # 초과분은 (룰 - 기준선) 이라 양쪽의 거래비용이 상쇄된다 → 비용 차감 없음.
    rows = [_day("2026-07-01", [_m("A", 2.0)])]
    s = _recompute_stats(rows, {"2026-07-01": (4.0, 3)})   # 나머지 2종목 합 2.0 → 평균 1.0
    assert s["mean_exc"] == 1.0                             # 2.0 - 1.0, 비용 미차감
    assert s["mean_net"] == round(2.0 - EDGE_COST_PCT, 3)   # 원시엔 비용 차감


def test_excess_multi_stock_day_uses_one_shared_baseline():
    # 유니버스 5종목 합 10.0, 매칭 A(4)·B(6) → 나머지 3종목 합 0.0, 평균 0.0.
    rows = [_day("2026-07-01", [_m("A", 4.0), _m("B", 6.0)])]
    s = _recompute_stats(rows, {"2026-07-01": (10.0, 5)})
    assert s["n_exc"] == 2
    assert s["mean_exc"] == 5.0          # (4-0 + 6-0)/2


def test_day_with_no_remaining_universe_is_dropped_from_excess():
    # 매칭이 유니버스 전체면 비교 대상이 없다 → 그날은 초과 표본에서 제외(원시엔 남음).
    rows = [_day("2026-07-01", [_m("A", 1.0), _m("B", 2.0)]),
            _day("2026-07-02", [_m("A", 3.0)])]
    uni = {"2026-07-01": (3.0, 2), "2026-07-02": (9.0, 3)}
    s = _recompute_stats(rows, uni)
    assert s["n"] == 3            # 원시는 3 표본 전부
    assert s["n_exc"] == 1        # 초과는 7/02 의 A 하나뿐
    assert s["mean_exc"] == 0.0   # 3.0 - (9-3)/2 = 0.0


def test_missing_universe_totals_leave_excess_none_fail_closed():
    # 기준선을 못 구하면 초과 계열은 None → check_promotion 이 fail-closed 로 막는다.
    rows = [_day("2026-07-01", [_m("A", 5.0)])]
    for uni in (None, {}, {"2026-07-09": (1.0, 2)}):
        s = _recompute_stats(rows, uni)
        assert s["n_exc"] == 0
        assert s["mean_exc"] is None and s["t_days_exc"] is None and s["ci_low_exc"] is None


def test_excess_t_days_is_day_equal_weighted():
    # 매칭 수가 많은 날에 쏠리지 않도록 t 는 '하루 1표본'으로 묶어 계산한다.
    rows = [_day("2026-07-01", [_m("A", 3.0), _m("B", 3.0), _m("C", 3.0)]),
            _day("2026-07-02", [_m("D", 1.0)]),
            _day("2026-07-03", [_m("E", 2.0)])]
    uni = {"2026-07-01": (9.0, 4), "2026-07-02": (1.0, 2), "2026-07-03": (2.0, 2)}
    # 각 날 나머지 1종목 수익 0 → 기준선 0 → 일별 초과 3.0, 1.0, 2.0
    s = _recompute_stats(rows, uni)
    assert s["mean_exc_days"] == 2.0                 # (3+1+2)/3, 종목수 가중이면 2.4
    assert s["t_days_exc"] == round(2.0 / (1.0 / 3 ** 0.5), 2)


def test_single_day_has_no_t_but_keeps_mean():
    s = _recompute_stats([_day("2026-07-01", [_m("A", 5.0)])], {"2026-07-01": (5.0, 2)})
    assert s["mean_exc"] is not None
    assert s["t_days_exc"] is None   # 거래일 1일 → 분산 추정 불가


# ── 판정 구간 슬라이스 (발견 1~10 / 확인 11~20) ──
# 판정 시점은 달력일이 아니라 **표본이 있는 거래일** 기준이다. 매칭이 드문 rule 은 달력으로
# 끊으면 표본 없이 판정일이 지나간다. 표본 없는 날을 세면 구간이 어긋나므로 계약을 고정한다.

def test_slice_counts_only_days_with_labeled_samples():
    rows = [_day("d1", [_m("A", 1.0)]),
            _day("d2", []),                       # 매칭 없음 — 세지 않음
            _day("d3", [_m("B", None)]),          # 라벨 미도래 — 세지 않음
            _day("d4", [_m("C", 2.0)]),
            _day("d5", [_m("D", 3.0)])]
    assert [r["report_date"] for r in _slice_sample_days(rows, 0, 2)] == ["d1", "d4"]
    assert [r["report_date"] for r in _slice_sample_days(rows, 2, 4)] == ["d5"]
    assert _slice_sample_days(rows, 5, None) == []


def test_slice_windows_are_disjoint_so_confirm_uses_fresh_samples():
    # 확인창이 발견 구간과 겹치면 '새 표본으로 확증'이라는 전제가 깨진다.
    rows = [_day(f"d{i}", [_m("A", float(i))]) for i in range(6)]
    disc = _slice_sample_days(rows, 0, 3)
    conf = _slice_sample_days(rows, 3, 6)
    assert [r["report_date"] for r in disc] == ["d0", "d1", "d2"]
    assert [r["report_date"] for r in conf] == ["d3", "d4", "d5"]
    assert not ({r["report_date"] for r in disc} & {r["report_date"] for r in conf})


def test_slice_is_stable_when_later_days_are_appended():
    # 재계산 시 같은 발견 구간이 재현돼야 한다(뒤에 날이 붙어도 앞 구간은 불변).
    base = [_day(f"d{i}", [_m("A", 1.0)]) for i in range(4)]
    grown = base + [_day("d9", [_m("A", 9.0)])]
    assert _slice_sample_days(base, 0, 3) == _slice_sample_days(grown, 0, 3)
