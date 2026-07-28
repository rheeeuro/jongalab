"""Edge Ledger 정책(core/edge_policy.py) 단위 테스트.

rule 역할(role·구 family 폴백) · 선정 시점 실행 가능성 · 승격 게이트(check_promotion)·강등 게이트(check_demotion)의 계약 고정.
게이트는 라우터(409 사유)·평가기(알림·promo_eligible)·프론트(배지)가 공유하는 단일 소스라
여기가 깨지면 세 곳이 동시에 어긋난다. 순수 로직이라 DB 무의존.
"""
from core.edge_policy import (
    ROLES,
    FAMILIES,
    rule_role,
    selection_executable,
    check_promotion,
    check_demotion,
    PROMO_MIN_DAY_T,
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


GOOD_STATS = {"n": 50, "n_days": 12, "ci_low": 0.1, "mean_net": 0.5, "t_days": 2.1}


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
    # 도메인 10종 — family 추가 시 이 레지스트리부터 갱신(라우터 등록 검증이 참조)
    assert set(FAMILIES) == {
        "f1_news", "f2_global", "f3_nxt", "f4_laggard", "f5_supply", "f6_ah",
        "f7_risk", "f8_value", "f9_disc", "control",
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
        _rule(stats={"n": 10, "n_days": 12, "ci_low": -0.1, "mean_net": 0.5, "t_days": 2.1}),
        [_control(0.2)],
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

# veto 실익 입증 통계 — 거래일 충족 + 제외 종목 평균이 음수(제외가 손실을 걸러냄).
GOOD_VETO_STATS = {"n": 12, "n_days": 11, "mean_net": -0.8, "ci_low": -2.1}


def test_veto_eligible_with_benefit_stats_and_executable():
    # veto 는 selector 급 검증(min_sample·CI·대조군)은 면제 — 대조군 없이도, ci_low 가
    # 음수여도 실익 게이트(n_days + mean_net<0)와 실행 가능성만 충족하면 승격 후보.
    ok_rule = _rule(family="f1_news", role="veto", stats=GOOD_VETO_STATS,
                    predicate=[{"col": "news_sentiment", "op": "<=", "value": 30}])
    gate = check_promotion(ok_rule, [])
    assert gate["eligible"] and gate["stat_reasons"] == [] and gate["exec_reasons"] == []


def test_veto_blocked_without_benefit_evidence():
    # veto_bio 사례(2026-07-13): 등록 당일 1거래일 n=3, 제외 종목 평균 +0.01% —
    # 완전 면제였다면 매일 '승격 후보' 알림. 거래일 부족 + 실익 미입증 둘 다 걸려야 한다.
    day_one = _rule(family="f7_risk", role="veto",
                    stats={"n": 3, "n_days": 1, "mean_net": 0.012, "ci_low": -1.541},
                    predicate=[{"col": "is_bio", "op": "==", "value": 1}])
    gate = check_promotion(day_one, [])
    assert not gate["eligible"]
    assert any("거래일 부족" in r for r in gate["stat_reasons"])
    assert any("실익 미입증" in r for r in gate["stat_reasons"])

    # 거래일은 쌓였어도 제외 종목이 평균 상승이면(veto 가 이득을 걸러낸 증거 없음) 차단.
    no_benefit = _rule(family="f7_risk", role="veto",
                       stats={"n": 30, "n_days": 12, "mean_net": 0.4, "ci_low": -0.5},
                       predicate=[{"col": "is_bio", "op": "==", "value": 1}])
    gate2 = check_promotion(no_benefit, [])
    assert not gate2["eligible"]
    assert any("실익 미입증" in r for r in gate2["stat_reasons"])

    # stats 미평가(None)도 fail-closed.
    gate3 = check_promotion(
        _rule(family="f1_news", role="veto", stats=None,
              predicate=[{"col": "news_sentiment", "op": "<=", "value": 30}]), [])
    assert not gate3["eligible"]


def test_veto_blocked_on_non_executable_predicate():
    dead_rule = _rule(family="f3_nxt", role="veto", stats=GOOD_VETO_STATS,
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


# ── 강등 게이트 (check_demotion) ──
# 역할별로 recent_mean_net 의 부호 의미가 반대다. 부호를 공유하면 잘 작동하는 veto 를 매일
# 강등 후보로 올린다(2026-07-28 veto_bio_kosdaq recent_mean_net=-0.158 오탐 알림).

def _live(role, recent_mean_net, recent_n=29, recent_n_days=10, family="f7_risk"):
    return {"name": "r", "family": family, "role": role, "status": "live",
            "stats": {"recent_n": recent_n, "recent_n_days": recent_n_days,
                      "recent_mean_net": recent_mean_net}}


def test_veto_demotion_sign_is_inverted_vs_selector():
    # veto 의 mean_net 은 '제외한' 종목의 순수익 — 음수는 손실을 제대로 걸러낸 것(승격 조건과
    # 같은 방향)이라 강등이 아니고, 양수여야 이기는 종목을 버리는 중 = 강등 검토.
    assert not check_demotion(_live("veto", -0.158))["demote_candidate"]
    assert check_demotion(_live("veto", 0.42))["demote_candidate"]


def test_selector_demoted_on_negative_recent_mean():
    assert check_demotion(_live("selector", -0.5, family="f4_laggard"))["demote_candidate"]
    assert not check_demotion(_live("selector", 0.5, family="f4_laggard"))["demote_candidate"]


def test_benchmark_never_demote_candidate():
    # live 대조군이 사라지면 check_promotion 의 '대조군 우위'가 fail-closed 로 전 후보를 막는다.
    assert not check_demotion(_live("benchmark", -0.494, family="control"))["demote_candidate"]


def test_demotion_requires_min_sample_and_days():
    assert not check_demotion(_live("veto", 0.42, recent_n=19))["demote_candidate"]
    assert not check_demotion(_live("veto", 0.42, recent_n_days=4))["demote_candidate"]
    assert not check_demotion(_live("veto", None))["demote_candidate"]
    assert not check_demotion({"name": "r", "family": "f7_risk", "role": "veto",
                               "status": "live", "stats": None})["demote_candidate"]


# ── 일 클러스터 t 게이트 (selector 전용, 2026-07-28) ──

def test_selector_blocked_on_weak_day_cluster_t():
    # f4_sector_follower 실례: iid ci_low(+0.21)·mean_net(+1.19%)은 통과인데 일 클러스터
    # t=0.37 — 수익이 시장 베타라 거래일 단위로는 유의하지 않다.
    gate = check_promotion(
        _rule(family="f4_laggard",
              stats={"n": 52, "n_days": 10, "ci_low": 0.207, "mean_net": 1.192, "t_days": 0.37}),
        [_control(-0.227)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_selector_day_cluster_t_is_fail_closed_when_missing():
    # 거래일 1일 등으로 분산 추정 불가(None) → 규율이 조용히 증발하지 않도록 차단.
    stats = dict(GOOD_STATS); stats["t_days"] = None
    gate = check_promotion(_rule(stats=stats), [_control(0.2)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_selector_passes_at_day_cluster_threshold():
    stats = dict(GOOD_STATS); stats["t_days"] = PROMO_MIN_DAY_T
    assert check_promotion(_rule(stats=stats), [_control(0.2)])["eligible"]


def test_veto_exempt_from_day_cluster_t():
    # veto 는 reduce-only + 가치가 꼬리 차단이라 평균 t 를 요구하지 않는다(veto_bio_kosdaq
    # 은 대체효과 t=0.95 로 평균 유의성이 없는데도 HLB 하한가 때문에 유지가 맞았다).
    gate = check_promotion(
        _rule(family="f7_risk", role="veto",
              stats={"n": 36, "n_days": 11, "mean_net": -0.203, "t_days": -0.4},
              predicate=[{"col": "is_bio", "op": "==", "value": 1}]), [])
    assert gate["eligible"]
