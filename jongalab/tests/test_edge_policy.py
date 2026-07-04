"""Edge Ledger 정책(core/edge_policy.py) 단위 테스트.

family 역할 레지스트리 · 선정 시점 실행 가능성 · 승격 게이트(check_promotion)의 계약 고정.
게이트는 라우터(409 사유)·평가기(알림·promo_eligible)·프론트(배지)가 공유하는 단일 소스라
여기가 깨지면 세 곳이 동시에 어긋난다. 순수 로직이라 DB 무의존.
"""
from core.edge_policy import (
    FAMILY_ROLES,
    family_role,
    selection_executable,
    check_promotion,
)


def _rule(family="f1_news", predicate=None, stats=None, min_sample=40):
    return {
        "name": "r", "family": family, "min_sample": min_sample,
        "predicate": predicate if predicate is not None
        else [{"col": "change_pct", "op": ">=", "value": 2}],
        "stats": stats,
    }


def _control(mean_net):
    return {"name": "control", "family": "control", "status": "live",
            "stats": {"mean_net": mean_net}}


GOOD_STATS = {"n": 50, "ci_low": 0.1, "mean_net": 0.5}


# ── family 역할 ──

def test_family_roles_cover_all_known_families():
    assert family_role("f3_nxt") == "selector"
    assert family_role("veto") == "veto"
    assert family_role("control") == "benchmark"
    assert family_role("unknown") is None
    # selector 4 + veto 1 + benchmark 1 — family 추가 시 이 레지스트리부터 갱신
    assert len(FAMILY_ROLES) == 6


# ── 선정 시점 실행 가능성 ──

def test_selection_executable_ok_for_selection_time_cols():
    ok, missing = selection_executable([
        {"col": "change_pct", "op": ">=", "value": 15},
        {"col": "news_sentiment", "op": "<=", "value": 30},
    ])
    assert ok and missing == []


def test_selection_executable_rejects_1950_and_market_cols():
    ok, missing = selection_executable([
        {"col": "change_pct", "op": ">=", "value": 15},
        {"col": "nxt_gap_pct", "op": ">=", "value": 5},       # 19:50 수집
        {"col": "market.sox_ret", "op": ">=", "value": 1.5},  # market_snapshot
    ])
    assert not ok
    assert missing == ["nxt_gap_pct", "market.sox_ret"]


# ── 승격 게이트: selector ──

def test_selector_eligible_when_all_gates_pass():
    gate = check_promotion(_rule(stats=GOOD_STATS), [_control(0.2)])
    assert gate["eligible"]
    assert gate["stat_reasons"] == [] and gate["exec_reasons"] == []


def test_selector_blocked_on_small_sample_and_ci():
    gate = check_promotion(_rule(stats={"n": 10, "ci_low": -0.1, "mean_net": 0.5}), [_control(0.2)])
    assert not gate["eligible"]
    assert len(gate["stat_reasons"]) == 2  # 표본 부족 + CI 하한


def test_selector_blocked_when_control_missing_fail_closed():
    # 대조군 부재/미평가는 fail-open(검사 생략)이 아니라 fail-closed(승격 불가)여야 한다.
    gate = check_promotion(_rule(stats=GOOD_STATS), [])
    assert not gate["eligible"]
    assert any("대조군 부재" in r for r in gate["stat_reasons"])

    gate2 = check_promotion(_rule(stats=GOOD_STATS), [_control(None)])
    assert not gate2["eligible"]


def test_selector_blocked_when_below_best_control():
    # 대조군이 여럿이면 최고 mean_net 을 이겨야 한다.
    gate = check_promotion(_rule(stats=GOOD_STATS), [_control(0.2), _control(0.9)])
    assert not gate["eligible"]
    assert any("대조군 우위" in r for r in gate["stat_reasons"])


def test_selector_blocked_on_non_executable_predicate():
    # veto_overheat_gap 사례: 통계가 아무리 좋아도 19:50 피처면 live 는 무음 no-op → 차단.
    rule = _rule(family="f3_nxt", stats=GOOD_STATS,
                 predicate=[{"col": "nxt_gap_pct", "op": ">=", "value": 3}])
    gate = check_promotion(rule, [_control(0.2)])
    assert not gate["eligible"]
    assert gate["stat_reasons"] == []      # 통계는 충족 → '집행 설계 필요' 알림 분기
    assert len(gate["exec_reasons"]) == 1


# ── 승격 게이트: veto / benchmark ──

def test_veto_skips_stat_gates_but_requires_executable():
    # veto 는 reduce-only 라 통계 게이트 면제 — 단 선정 시점 실행은 가능해야 한다.
    ok_rule = _rule(family="veto", stats=None,
                    predicate=[{"col": "news_sentiment", "op": "<=", "value": 30}])
    assert check_promotion(ok_rule, [])["eligible"]

    dead_rule = _rule(family="veto", stats=None,
                      predicate=[{"col": "nxt_gap_pct", "op": ">=", "value": 5}])
    gate = check_promotion(dead_rule, [])
    assert not gate["eligible"] and gate["exec_reasons"]


def test_benchmark_exempt_from_all_gates():
    # 대조군 교체는 실탄 배정이 아니라 기준선 교체 — 통계·실행 게이트 모두 면제.
    rule = _rule(family="control", stats=None,
                 predicate=[{"col": "selected", "op": "==", "value": 1}])
    assert check_promotion(rule, [])["eligible"]
