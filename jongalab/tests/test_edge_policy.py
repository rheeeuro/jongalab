"""Edge Ledger 정책(core/edge_policy.py) 단위 테스트.

rule 역할(role·구 family 폴백) · 선정 시점 실행 가능성 · 승격 게이트(check_promotion)의 계약 고정.
게이트는 라우터(409 사유)·평가기(알림·promo_eligible)·프론트(배지)가 공유하는 단일 소스라
여기가 깨지면 세 곳이 동시에 어긋난다. 순수 로직이라 DB 무의존.
"""
from core.edge_policy import (
    ROLES,
    FAMILIES,
    rule_role,
    selection_executable,
    check_promotion,
)


def _rule(family="f1_news", role=None, predicate=None, stats=None, min_sample=40):
    r = {
        "name": "r", "family": family, "min_sample": min_sample,
        "predicate": predicate if predicate is not None
        else [{"col": "change_pct", "op": ">=", "value": 2}],
        "stats": stats,
    }
    if role is not None:
        r["role"] = role
    return r


def _control(mean_net):
    return {"name": "control", "family": "control", "role": "benchmark", "status": "live",
            "stats": {"mean_net": mean_net}}


GOOD_STATS = {"n": 50, "n_days": 12, "ci_low": 0.1, "mean_net": 0.5}


# ── rule 역할 ──

def test_rule_role_prefers_explicit_role_column():
    # role 명시 시 family 와 무관하게 role 이 이긴다 — 수급 밴드(f5_supply + benchmark) 사례.
    assert rule_role({"family": "f5_supply", "role": "benchmark"}) == "benchmark"
    assert rule_role({"family": "f5_supply", "role": "veto"}) == "veto"
    assert rule_role({"family": "f6_ah", "role": "selector"}) == "selector"


def test_rule_role_falls_back_to_legacy_family_mapping():
    # role 컬럼 도입(sql/15) 전 스키마/구 dict — family 겸용 매핑으로 폴백.
    assert rule_role({"family": "f3_nxt"}) == "selector"
    assert rule_role({"family": "veto"}) == "veto"
    assert rule_role({"family": "control"}) == "benchmark"
    assert rule_role({"family": "unknown"}) is None
    # 알 수 없는 role 값도 폴백(오타가 무음 selector 가 되는 걸 방지)
    assert rule_role({"family": "control", "role": "banchmark"}) == "benchmark"


def test_role_and_family_registries():
    assert set(ROLES) == {"selector", "veto", "benchmark"}
    # 도메인 7종 — family 추가 시 이 레지스트리부터 갱신(라우터 등록 검증이 참조)
    assert set(FAMILIES) == {
        "f1_news", "f2_global", "f3_nxt", "f4_laggard", "f5_supply", "f6_ah", "control",
    }
    assert "veto" not in FAMILIES  # 역할은 family 가 아니다(2026-07-09 분리)


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
    gate = check_promotion(
        _rule(stats={"n": 10, "n_days": 12, "ci_low": -0.1, "mean_net": 0.5}), [_control(0.2)]
    )
    assert not gate["eligible"]
    assert len(gate["stat_reasons"]) == 2  # 표본 부족 + CI 하한


def test_selector_blocked_on_few_trading_days():
    # f5_supply_band_d 사례: 광역 rule 은 2거래일 만에 n=70 을 채우지만 같은 날 표본은
    # 시장 무브로 상관 — 종목-일 n 이 아니라 거래일 수(n_days)가 실효 표본이다.
    few_days = {"n": 70, "n_days": 2, "ci_low": 0.46, "mean_net": 1.25}
    gate = check_promotion(_rule(stats=few_days), [_control(0.2)])
    assert not gate["eligible"]
    assert any("거래일 부족" in r for r in gate["stat_reasons"])

    # n_days 미기록(구 stats) 도 fail-closed — evaluator 다음 실행이 채우면 자연 해소.
    gate2 = check_promotion(_rule(stats={"n": 50, "ci_low": 0.1, "mean_net": 0.5}), [_control(0.2)])
    assert not gate2["eligible"]
    assert any("거래일 부족" in r for r in gate2["stat_reasons"])


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
    # role 분리 후 veto 는 도메인 family(f1_news 등) + role='veto' 로 표현된다.
    ok_rule = _rule(family="f1_news", role="veto", stats=None,
                    predicate=[{"col": "news_sentiment", "op": "<=", "value": 30}])
    assert check_promotion(ok_rule, [])["eligible"]

    dead_rule = _rule(family="f3_nxt", role="veto", stats=None,
                      predicate=[{"col": "nxt_gap_pct", "op": ">=", "value": 5}])
    gate = check_promotion(dead_rule, [])
    assert not gate["eligible"] and gate["exec_reasons"]


def test_benchmark_exempt_from_all_gates():
    # 대조군 교체는 실탄 배정이 아니라 기준선 교체 — 통계·실행 게이트 모두 면제.
    rule = _rule(family="control", role="benchmark", stats=None,
                 predicate=[{"col": "selected", "op": "==", "value": 1}])
    assert check_promotion(rule, [])["eligible"]


def test_supply_band_as_benchmark_skips_selector_gates():
    # 수급 밴드(f5_supply + role=benchmark): 광역 매칭 측정 도구가 selector 통계 게이트를
    # 우연히 통과해 실탄 선정에 승격되는 경로를 role 분리가 차단한다.
    band = _rule(family="f5_supply", role="benchmark", stats=GOOD_STATS,
                 predicate=[{"col": "supply_score", "op": "between", "value": [0, 40]}])
    gate = check_promotion(band, [])
    assert gate["eligible"] and gate["stat_reasons"] == [] and gate["exec_reasons"] == []
