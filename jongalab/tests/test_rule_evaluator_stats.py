"""workers/rule_evaluator._recompute_stats 계약 고정 — 순수 집계(DB·네트워크 무의존).

게이트가 쓰는 원시 계열(mean_net·ci_low·t_days)과, **룰 상세 화면 표기 전용**인 유니버스
자기제외 초과 계열(mean_exc·ci_low_exc·t_days_exc, 2026-07-28 도입 / 2026-08-04 게이트에서
제외)을 함께 고정한다. 초과 계열은 이제 판정에 쓰지 않지만 "장 덕에 올랐나"를 사람이 보는
값이라 정확해야 한다 — 자기제외를 빼먹으면 rule 이 자기 자신을 기준선에 넣어 초과분이 0 쪽으로
눌리는데(대조군 기준 시 겹침 평균 54%·일부 100%), 그게 이 테스트의 핵심 표적이다.
"""
from core.config import EDGE_COST_PCT
from core.edge_policy import DEMOTE_MIN_N
from workers.rule_evaluator import _recompute_stats, _recent_window, _slice_sample_days


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
    assert s["n"] == 0 and s["n_exc"] == 0 and s["down_day_n"] == 0
    for k in ("mean_net", "ci_low", "t_days", "mean_exc", "ci_low_exc", "t_days_exc",
              "beta", "alpha", "t_alpha", "recent_alpha", "down_day_mean"):
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


# ── 시장 회귀 계열(alpha·beta) — 강등 게이트가 recent_alpha 를 쓴다 ──
# 초과수익(mean_exc)은 beta=1 을 강제해 저beta 방어형 룰을 상승장에서 죽인다. 그 문제를
# 푸는 게 alpha 이고, 아래 두 테스트가 "초과로는 죽지만 alpha 로는 산다"를 못 박는다.

def _mkt_days(pairs, code="A"):
    """(시장 평균, 룰 종목 수익) 목록 → (daily_rows, uni_totals).

    유니버스는 룰 매칭 1종목 + 나머지 2종목으로 만든다. 나머지 2종목 합을 조절해
    자기제외 평균(= 그날 시장)이 원하는 값이 되게 한다.
    """
    rows, totals = [], {}
    for i, (mkt, ret) in enumerate(pairs):
        d = f"2026-07-{i + 1:02d}"
        rows.append(_day(d, [_m(code, ret)]))
        totals[d] = (ret + mkt * 2, 3)   # 자기제외: (합 - ret)/2 = mkt
    return rows, totals


def test_beta_and_alpha_recover_a_known_line():
    # 룰수익 = 0.5 + 0.5 x 시장 을 정확히 따르는 표본 → beta 0.5, alpha 0.5 - 비용.
    mkts = [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    rows, totals = _mkt_days([(m, 0.5 + 0.5 * m) for m in mkts])
    s = _recompute_stats(rows, totals)
    assert s["beta"] == 0.5
    # alpha 는 룰 쪽에만 비용이 차감되므로 그만큼 내려간다(순수익 기준 alpha).
    assert s["alpha"] == round(0.5 - EDGE_COST_PCT, 3)


def test_low_beta_defensive_rule_has_negative_excess_but_positive_alpha():
    """사용자가 짚은 반례 — 상승장에서 시장보다 덜 벌지만 하락장엔 플러스인 룰.

    시장이 대체로 강세(+3%)인 구간에서 이 룰은 +1% 에 그쳐 **초과수익은 음수**다.
    beta 가 낮아서 그런 것이고 alpha 는 양수다 — 초과 기준 강등은 이 룰을 죽이고,
    alpha 기준 강등은 살린다.
    """
    rows, totals = _mkt_days([(3.0, 1.0), (3.0, 1.0), (-2.0, 0.0),
                              (3.0, 1.0), (-2.0, 0.0), (3.0, 1.0)])
    s = _recompute_stats(rows, totals)
    assert s["mean_exc"] < 0          # 초과 기준으로는 죽는다
    assert s["beta"] < 0.5            # 시장을 덜 따라간다
    assert s["alpha"] > 0             # 시장 몫을 beta 만큼만 빼면 양수
    assert s["recent_alpha"] > 0      # 강등 게이트가 보는 값도 양수
    # 하락일(시장<0) 성적이 손실이 아니다 — "잃지 않고" 를 직접 재는 표기값.
    assert s["down_day_n"] == 2 and s["down_day_mean"] == round(-EDGE_COST_PCT, 3)


def test_high_beta_rule_is_negative_alpha_even_while_absolute_is_positive():
    # 상승장 덕에 절대 수익은 플러스지만 시장 몫을 빼면 마이너스인 고beta 룰.
    # 절대 자(recent_mean_net<0)로는 상승 구간에 절대 안 걸리는 유형이다.
    rows, totals = _mkt_days([(2.0, 2.0), (3.0, 3.2), (2.0, 1.8),
                              (4.0, 4.5), (1.0, 0.5), (3.0, 3.0)])
    s = _recompute_stats(rows, totals)
    assert s["mean_net"] > 0          # 절대 수익은 플러스
    assert s["beta"] > 1.0            # 시장을 증폭해서 탄다
    assert s["alpha"] < 0 and s["recent_alpha"] < 0   # 시장 몫을 빼면 마이너스


def test_market_fit_needs_min_days_and_variance():
    # 거래일 4일(<_FIT_MIN_DAYS=5) → 추정하지 않는다(fail-closed).
    rows, totals = _mkt_days([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)])
    s = _recompute_stats(rows, totals)
    assert s["beta"] is None and s["alpha"] is None and s["recent_alpha"] is None
    # 시장 분산이 0 이면 기울기를 못 구한다.
    rows, totals = _mkt_days([(1.0, 0.5), (1.0, 1.5), (1.0, 0.5), (1.0, 1.5), (1.0, 1.0)])
    s = _recompute_stats(rows, totals)
    assert s["beta"] is None and s["recent_alpha"] is None


def test_market_fit_is_none_without_universe_totals():
    # 초과 기준선이 없으면 시장 계열도 못 만든다 → 강등 게이트가 fail-closed 로 멈춘다.
    rows = [_day(f"2026-07-{i:02d}", [_m("A", 1.0)]) for i in range(1, 7)]
    s = _recompute_stats(rows)
    assert s["beta"] is None and s["recent_alpha"] is None and s["down_day_n"] == 0


# ── 적응형 최근 창 (_recent_window) ──
# 창을 표본일 개수로만 고정하면 n = 표본일 x 폭 이라 **폭이 얇은 룰은 문턱을 영원히 못 넘고**
# 자동 전이 대상에서 영구히 빠진다. 창을 뒤로 늘려 문턱을 채우는 것이 이 함수의 존재 이유다.

def test_thick_rule_window_stays_at_the_minimum():
    # 하루 3종목씩 12일 — 10일이면 이미 n=30 이라 창이 늘지 않는다(기존 동작 불변).
    days = [(f"2026-07-{i:02d}", 3) for i in range(1, 13)]
    assert len(_recent_window(days)) == 10


def test_thin_rule_window_extends_until_the_sample_threshold():
    # 하루 1종목씩 30일 — 10일 창이면 n=10 으로 문턱(20) 미달이라 20일까지 늘어난다.
    days = [(f"2026-07-{i:02d}", 1) for i in range(1, 31)]
    w = _recent_window(days)
    assert len(w) == DEMOTE_MIN_N
    assert "2026-07-30" in w and "2026-07-10" not in w   # 최신 쪽으로 붙어 있다


def test_window_stops_at_available_history_when_threshold_unreachable():
    # 표본이 아직 모자라면 있는 만큼만 — 문턱 미달이라 게이트가 '판정 불가'로 막는다.
    days = [(f"2026-07-{i:02d}", 1) for i in range(1, 13)]
    assert len(_recent_window(days)) == 12


def test_empty_history_has_no_window():
    assert _recent_window([]) == set()


def test_last_sample_date_ignores_days_with_no_matches():
    """자동 전이의 '새 정보가 있었나' 판정용 값 — updated_through 와 **달라야** 한다.

    평가기는 매칭이 0 인 날에도 edge_rule_daily 행을 남기므로 updated_through 는 매 평일
    움직인다. 그걸로 연속을 세면 alpha 가 안 바뀐 날까지 세어져 단위가 표본일이 아니라
    달력 평일이 되고, 드문 룰이 새 표본 없이 전이한다.
    """
    rows = [
        _day("2026-07-01", [_m("A", 1.0)]),
        _day("2026-07-02", []),            # 매칭 0 — 행은 남지만 표본은 아니다
        _day("2026-07-03", []),
    ]
    s = _recompute_stats(rows)
    assert s["updated_through"] == "2026-07-03"
    assert s["last_sample_date"] == "2026-07-01"


def test_last_sample_date_is_none_without_any_sample():
    s = _recompute_stats([_day("2026-07-01", []), _day("2026-07-02", [])])
    assert s["n"] == 0 and s["last_sample_date"] is None
