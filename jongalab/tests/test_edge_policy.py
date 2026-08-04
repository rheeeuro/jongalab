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
    day_t_threshold,
    decision_stage,
    decision_due,
    check_confirmation,
    DISCOVERY_DAYS,
    CONFIRM_DAYS,
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
    """live 대조군. 2026-08-04 부터 **게이트는 대조군을 보지 않는다**(조건 제거) — 이 헬퍼는
    호출부 시그니처를 유지하며 '대조군이 무엇이든 판정이 바뀌지 않는다'를 고정하는 데 쓴다.
    (구 동작 메모) 게이트는 **일 등가중**(mean_net_days)으로 비교했다 — 시드가 하루 총액
    고정·종목 등분이라 계좌 실현치가 그 값이기 때문(양쪽 같은 가중이어야 비교가 성립)."""
    return {"name": "control", "family": "control", "role": "benchmark", "status": "live",
            "stats": {"mean_net": mean_net, "mean_net_days": mean_net}}


# 2026-08-04: 게이트는 **절대 계열만** 본다(mean_net·ci_low·t_days). 초과 계열(mean_exc·
# ci_low_exc·t_days_exc)은 룰 상세 화면 표기 전용이라 여기서는 판정에 영향이 없다.
GOOD_STATS = {"n": 50, "n_days": 12, "mean_net": 0.5, "mean_net_days": 0.5,
              "ci_low": 0.1, "t_days": 2.1, "mean_exc": 0.3}


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


def test_selector_blocked_on_ci_but_not_on_stock_day_count():
    # 2026-07-28: min_sample(종목-일)은 게이트에서 빠졌다 — 단위가 거래일 기준 규율과 어긋나
    # 통계적으로 강한 좁은 룰(하루 1~2종목)을 막고 있었다. n=10 < min_sample=40 이어도
    # 그 자체로는 탈락 사유가 아니고, 남는 사유는 CI 하한뿐이다.
    gate = check_promotion(
        _rule(stats={"n": 10, "n_days": 12, "mean_net": 0.5, "mean_net_days": 0.5, "mean_exc": 0.3,
                     "ci_low": -0.1, "t_days": 2.1}),
        [_control(0.2)],
    )
    assert not gate["eligible"]
    assert len(gate["stat_reasons"]) == 1
    assert "신뢰구간" in gate["stat_reasons"][0]
    assert not any("min_sample" in r for r in gate["stat_reasons"])


def test_selector_blocked_on_few_trading_days():
    # f5_supply_band_d 사례: 광역 rule 은 2거래일 만에 n=70 을 채우지만 같은 날 표본은
    # 시장 무브로 상관 — 종목-일 n 이 아니라 거래일 수(n_days)가 실효 표본이다.
    few_days = {"n": 70, "n_days": 2, "ci_low": 0.46, "mean_net": 1.25, "mean_net_days": 1.25,
                "mean_exc": 0.5, "t_days": 2.5}
    gate = check_promotion(_rule(stats=few_days), [_control(0.2)])
    assert not gate["eligible"]
    assert any("거래일 부족" in r for r in gate["stat_reasons"])

    # n_days 미기록(구 stats) 도 fail-closed — evaluator 다음 실행이 채우면 자연 해소.
    gate2 = check_promotion(_rule(stats={"n": 50, "ci_low": 0.1, "mean_net": 0.5}), [_control(0.2)])
    assert not gate2["eligible"]
    assert any("거래일 부족" in r for r in gate2["stat_reasons"])


# ── 대조군 우위 제거 (2026-08-04 사용자 결정) ──
# "평균보다 수익이 크지 않더라도 안정적으로 수익이 나면 그만" — 현행 선정(대조군)을 못 이겨도
# 그 자체로 돈을 버는 rule 은 실탄에 올린다. 게이트는 이제 대조군을 아예 보지 않는다.

def test_control_is_not_a_gate_condition():
    # 대조군이 없어도(구 동작에서는 fail-closed) 판정은 통계만으로 결정된다.
    gate = check_promotion(_rule(stats=GOOD_STATS), [])
    assert gate["eligible"], gate["stat_reasons"]
    assert not any("대조군" in r for r in gate["stat_reasons"])


def test_selector_passes_even_when_below_best_control():
    # 대조군 성적이 rule 보다 좋아도(0.9 > 0.5) 탈락 사유가 되지 않는다.
    gate = check_promotion(_rule(stats=GOOD_STATS), [_control(0.2), _control(0.9)])
    assert gate["eligible"], gate["stat_reasons"]
    assert not any("대조군" in r for r in gate["stat_reasons"])


def test_selector_blocked_on_non_executable_predicate():
    # 통계가 아무리 좋아도 **어느 레이어에서도** 못 쓰는 피처면 live 는 무음 no-op → 차단.
    # short_wght 는 17:50 수집이라 선정(13~15시)에도 NXT 집행(19:50)에도 없다.
    rule = _rule(family="f7_risk", role="selector", stats=GOOD_STATS,
                 predicate=[{"col": "short_wght", "op": ">=", "value": 15}])
    gate = check_promotion(rule, [_control(0.2)])
    assert not gate["eligible"]
    assert gate["stat_reasons"] == []      # 통계는 충족 → '집행 설계 필요' 알림 분기
    assert len(gate["exec_reasons"]) == 1


def test_nxt_gap_rule_is_promotable_via_execution_layer():
    """19:50 갭은 **집행 레이어**에서 평가 가능하므로 승격을 막지 않는다 (2026-08-03).

    NXT 매수는 19:50 데드라인 단일 주문이고 집행기가 그 순간 갭을 계산해 predicate 에 먹인다
    (trading `core/edge_execution`). 이 예외가 없던 동안 원장에서 통계가 가장 강한
    `f3_nxt_gap_quality`(초과 t=2.21)가 영구 승격 불가였고, 그 가설을 쓰려면 원장을 우회한
    하드코딩이 필요했다(= 채점·강등 감시 소실).
    """
    rule = _rule(family="f3_nxt", stats=GOOD_STATS, predicate=[
        {"col": "nxt_gap_pct", "op": "between", "value": [1.0, 6.0]},
        {"col": "nxt_listed", "op": "==", "value": 1},
        {"col": "sector_rel_ret", "op": ">=", "value": 0},
        {"col": "change_pct", "op": "between", "value": [0, 12]},
    ])
    gate = check_promotion(rule, [_control(0.2)])
    assert gate["exec_reasons"] == []
    assert gate["eligible"]


def test_rule_layer_prefers_selection_over_execution():
    from core.edge_policy import rule_layer
    # 선정 시점에 되는 rule 은 선정 레이어 — 집행으로 내리면 대체가 안 돼 시드가 논다.
    assert rule_layer([{"col": "supply_score", "op": ">=", "value": 50}]) == "selection"
    assert rule_layer([{"col": "nxt_gap_pct", "op": ">=", "value": 1}]) == "execution"
    # 섞이면 가장 늦은 레이어(집행)에서만 가능
    assert rule_layer([{"col": "supply_score", "op": ">=", "value": 50},
                       {"col": "nxt_gap_pct", "op": ">=", "value": 1}]) == "execution"
    # 17:50·익일 수집은 어느 레이어에서도 불가
    assert rule_layer([{"col": "short_wght", "op": ">=", "value": 15}]) is None
    assert rule_layer([{"col": "next_open_ret", "op": ">", "value": 0}]) is None
    # market.* 는 선정 시점 스냅샷이 없어 여전히 불가(기존 규약 유지)
    assert rule_layer([{"col": "market.vix", "op": ">", "value": 20}]) is None


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
    # 17:50 수집(short_wght)은 선정에도 NXT 집행에도 없다 → veto 여도 무음 no-op.
    dead_rule = _rule(family="f7_risk", role="veto", stats=GOOD_VETO_STATS,
                      predicate=[{"col": "short_wght", "op": ">=", "value": 15}])
    gate = check_promotion(dead_rule, [])
    assert not gate["eligible"] and gate["exec_reasons"]


def test_veto_on_nxt_gap_is_promotable_via_execution_layer():
    # veto 도 집행 레이어에서 평가 가능하면 실행 게이트를 통과한다(2026-08-03).
    live_veto = _rule(family="f3_nxt", role="veto", stats=GOOD_VETO_STATS,
                      predicate=[{"col": "nxt_gap_pct", "op": "<", "value": 0}])
    assert check_promotion(live_veto, [])["eligible"]


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
    """live rule. 강등 게이트도 승격과 같은 가중(일 등가중)을 본다."""
    return {"name": "r", "family": family, "role": role, "status": "live",
            "stats": {"recent_n": recent_n, "recent_n_days": recent_n_days,
                      "recent_mean_net": recent_mean_net,
                      "recent_mean_net_days": recent_mean_net}}


def test_veto_demotion_sign_is_inverted_vs_selector():
    # veto 의 mean_net 은 '제외한' 종목의 순수익 — 음수는 손실을 제대로 걸러낸 것(승격 조건과
    # 같은 방향)이라 강등이 아니고, 양수여야 이기는 종목을 버리는 중 = 강등 검토.
    assert not check_demotion(_live("veto", -0.158))["demote_candidate"]
    assert check_demotion(_live("veto", 0.42))["demote_candidate"]


def test_selector_demoted_on_negative_recent_mean():
    assert check_demotion(_live("selector", -0.5, family="f4_laggard"))["demote_candidate"]
    assert not check_demotion(_live("selector", 0.5, family="f4_laggard"))["demote_candidate"]


def test_benchmark_never_demote_candidate():
    # 페이퍼 기준선이라 유지 비용이 없고, 성적이 나쁜 것 자체가 정보다(대조군의 존재 이유).
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
              stats={"n": 52, "n_days": 10, "mean_net": 1.192, "mean_net_days": 1.192, "mean_exc": 0.79,
                     "ci_low": 0.207, "t_days": 0.37}),
        [_control(-0.227)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_selector_day_cluster_t_is_fail_closed_when_missing():
    # 거래일 1일 등으로 분산 추정 불가(None) → 규율이 조용히 증발하지 않도록 차단.
    stats = dict(GOOD_STATS); stats["t_days"] = None
    gate = check_promotion(_rule(stats=stats), [_control(0.2)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_day_cluster_threshold_uses_t_distribution_not_fixed_165():
    # 문턱은 고정 1.65 가 아니라 거래일 자유도의 t 임계값 — 소표본에서 더 엄격해야 한다.
    assert day_t_threshold(11) == 1.812      # 거래일 11 → df 10
    assert day_t_threshold(5) == 2.132       # 거래일 5  → df 4  (1.65 보다 훨씬 높다)
    assert day_t_threshold(1) is None        # 거래일 1  → 분산 추정 불가
    assert day_t_threshold(200) == 1.645     # 대표본 → 정규 극한
    # GOOD_STATS(n_days=12, df=11 → 1.796): 정규 1.65 는 이제 통과가 아니다.
    stats = dict(GOOD_STATS); stats["t_days"] = PROMO_MIN_DAY_T
    assert not check_promotion(_rule(stats=stats), [_control(0.2)])["eligible"]
    stats["t_days"] = day_t_threshold(12)
    assert check_promotion(_rule(stats=stats), [_control(0.2)])["eligible"]


def test_veto_exempt_from_day_cluster_t():
    # veto 는 reduce-only + 가치가 꼬리 차단이라 평균 t 를 요구하지 않는다(veto_bio_kosdaq
    # 은 대체효과 t=0.95 로 평균 유의성이 없는데도 HLB 하한가 때문에 유지가 맞았다).
    gate = check_promotion(
        _rule(family="f7_risk", role="veto",
              stats={"n": 36, "n_days": 11, "mean_net": -0.203, "t_days": -0.4},
              predicate=[{"col": "is_bio", "op": "==", "value": 1}]), [])
    assert gate["eligible"]


# ── 판정 일정: 발견 → 확인창 → 종결 (2026-07-28) ──
# 매일 재평가는 무기한 재시험이라 오탐이 명목 5% → 22% 가 된다. 판정을 사전 시점 1회로 묶는다.

def test_decision_stage_progresses_and_terminates():
    assert decision_stage({}) == "discovery"                       # 기록 없음 = 발견 전
    assert decision_stage({"decision": {"discovery": {"pass": True}}}) == "confirming"
    # 발견 탈락은 확인창으로 가지 않고 즉시 종결 — 재시험 금지
    assert decision_stage({"decision": {"discovery": {"pass": False}}}) == "decided"
    assert decision_stage({"decision": {"discovery": {"pass": True},
                                        "decided_at": "2026-07-28"}}) == "decided"


def test_decision_due_only_at_scheduled_points():
    fresh = {}
    assert decision_due(fresh, DISCOVERY_DAYS - 1) is None         # 아직 이름
    assert decision_due(fresh, DISCOVERY_DAYS) == "discovery"
    passed = {"decision": {"discovery": {"pass": True}}}
    assert decision_due(passed, DISCOVERY_DAYS) is None            # 확인창 표본 대기
    assert decision_due(passed, DISCOVERY_DAYS + CONFIRM_DAYS - 1) is None
    assert decision_due(passed, DISCOVERY_DAYS + CONFIRM_DAYS) == "confirm"


def test_decided_rule_is_never_retested():
    # 핵심 계약 — 한 번 판정한 rule 은 거래일이 아무리 쌓여도 다시 검사하지 않는다.
    done = {"decision": {"discovery": {"pass": True}, "confirm": {"pass": False},
                         "decided_at": "2026-07-28", "verdict": "confirm_failed"}}
    for nd in (10, 20, 50, 500):
        assert decision_due(done, nd) is None


def test_confirmation_requires_positive_mean_net_on_fresh_sample():
    # 2026-08-04: 확인창도 발견 게이트와 같은 자(절대 평균수익). 초과수익은 판정에 안 쓴다.
    assert check_confirmation({"mean_net": 0.4, "n_days": 10})["pass"]
    assert not check_confirmation({"mean_net": -0.1, "n_days": 10})["pass"]
    assert not check_confirmation({"mean_net": 0.0, "n_days": 10})["pass"]   # 0 은 미달
    # 초과수익이 음수여도(장이 더 올랐어도) 절대 수익이 양수면 재현으로 본다.
    assert check_confirmation({"mean_net": 0.4, "mean_exc": -1.2, "n_days": 10})["pass"]


def test_confirmation_fail_closed_without_samples():
    for s in (None, {}, {"n_days": 5}, {"n_days": 10, "mean_exc": 1.0}):
        r = check_confirmation(s)
        assert not r["pass"] and r["reasons"]


# ── 확인창 부호 (2026-07-29 수정) ──
# 확인창이 role 을 안 보면 veto 는 "제외할 종목이 벌어야 확증"이 된다. 즉 **잘 작동하는 veto 가
# 그 이유로 종결**된다(veto_short_surge 실례: 제외 종목 mean_net -0.38% = veto 로선 정상 방향인데
# confirm_failed 예정이었다). 자는 양쪽 다 mean_net 이고 **부호만** 반대다.

def test_veto_confirmation_requires_negative_raw_mean_on_fresh_sample():
    # veto 는 발견 게이트와 **같은 자**(제외 종목 mean_net<0)로 재확인한다.
    working = {"n_days": 10, "mean_net": -0.38, "mean_exc": -0.98}
    assert check_confirmation(working, "veto")["pass"]
    assert not check_confirmation(working, "selector")["pass"]   # selector 자로는 탈락(부호 반대)

    # 새 표본에서 제외 대상이 오히려 벌었다면 실익 미재현 → 탈락.
    broken = {"n_days": 10, "mean_net": 0.4, "mean_exc": 0.2}
    assert not check_confirmation(broken, "veto")["pass"]
    assert check_confirmation(broken, "selector")["pass"]

    assert not check_confirmation({"n_days": 10, "mean_net": 0.0}, "veto")["pass"]  # 0 은 미달


def test_veto_confirmation_fail_closed_without_raw_sample():
    # 초과 표본만 있고 평균수익이 없으면 veto 는 판정 불가 → fail-closed.
    for s in (None, {}, {"n_days": 5}, {"n_days": 10, "mean_exc": -1.0}):
        r = check_confirmation(s, "veto")
        assert not r["pass"] and r["reasons"]


# ── 평균수익 하한 (2026-07-28 도입, 2026-08-04 유일한 수익성 자로 승격) ──
# 초과수익이 좋아도 돈을 잃는 rule 은 올리지 않는다. 대조군 우위로도 막히지 않는다 —
# 대조군(control_legacy_top10) 자체가 음수인 구간이면 문턱이 음수이기 때문.

def test_selector_blocked_when_excess_positive_but_absolute_loses():
    # f5_late_day_strength 실례: 절대 -0.39% / 초과 +0.20%. 유의성이 아무리 좋아도 실탄 불가.
    losing = {"n": 79, "n_days": 11, "mean_net": -0.39, "mean_net_days": -0.39, "mean_exc": 0.20,
              "ci_low": 0.05, "t_days": 3.0}
    gate = check_promotion(_rule(family="f5_supply", stats=losing), [_control(-0.227)])
    assert not gate["eligible"]
    assert any("평균수익 미충족" in r for r in gate["stat_reasons"])


def test_beating_a_losing_control_is_not_enough():
    # 대조군이 -0.227% 라고 해서 -0.1% 인 rule 을 올리면 안 된다('덜 잃는 쪽' 선택 금지).
    # 대조군 조건이 사라진 뒤에는 **평균수익>0 이 이 방어선의 전부**라 더 중요해졌다.
    gate = check_promotion(
        _rule(stats={"n": 50, "n_days": 12, "mean_net": -0.1, "mean_net_days": -0.1, "mean_exc": 0.2,
                     "ci_low": 0.2, "t_days": 2.5}),
        [_control(-0.227)])
    assert not gate["eligible"]
    assert any("평균수익 미충족" in r for r in gate["stat_reasons"])
    # 대조군은 아예 판정에 안 들어간다(2026-08-04) → 평균수익 하한이 유일한 방어선
    assert not any("대조군" in r for r in gate["stat_reasons"])


def test_excess_return_is_not_a_gate_condition():
    # 2026-08-04 사용자 결정 — "평균보다 수익이 크지 않더라도 안정적으로 수익이 나면 그만".
    # 초과수익이 **음수**여도(같은 날 유니버스가 더 올랐어도) 평균수익·안정성을 충족하면
    # 통과한다. 초과 계열은 상세 화면 표기 전용이다.
    below_universe = {"n": 50, "n_days": 12, "mean_net": 1.5, "mean_net_days": 1.5,
                      "ci_low": 0.3, "t_days": 2.5,
                      "mean_exc": -0.8, "ci_low_exc": -1.9, "t_days_exc": -0.6}
    gate = check_promotion(_rule(stats=below_universe), [_control(-0.227)])
    assert gate["eligible"]
    assert not any("초과" in r for r in gate["stat_reasons"])

    # 반대로 절대 계열이 불안정하면(CI 하한 음수) 초과가 아무리 좋아도 막힌다(정책 무관).
    unstable = {"n": 50, "n_days": 12, "mean_net": 1.5, "mean_net_days": 1.5,
                "ci_low": -0.3, "t_days": 0.2,
                "mean_exc": 0.9, "ci_low_exc": 0.5, "t_days_exc": 2.9}
    assert not check_promotion(_rule(stats=unstable), [_control(-0.227)])["eligible"]


# ── 가중 방식 (2026-07-28 결정) ──
# 효과 크기(평균수익 하한·강등)는 **종목-일 가중**(mean_net) — 시드 배분을 반영하지
# 않는다. 근거: ① rule 채점은 유니버스 전체 대상이라 매칭 종목-일 대부분은 사지도 않은 종목
# → '그날 계좌 수익률' 개념이 성립하지 않는다. ② 시드 배분은 바뀌므로(SEED_MAX_NAME_PCT
# 50%→25% 이력) 측정이 배분에 의존하면 배분 변경 시 과거 점수가 무효가 된다.
# 쏠림(매칭 많은 날에 수익 집중)은 **유의성 쪽에서 t_days(일 등가중)가 잡는다.**

def test_absolute_floor_uses_stock_day_weighting_not_seed_logic():
    # mean_net_days 가 음수여도 게이트는 mean_net(종목-일)으로 판정한다 — 가설 검증을
    # 집행(시드 배분) 방식과 분리하기 위한 의도된 선택이다.
    concentrated = {"n": 23, "n_days": 12, "mean_net": 0.950, "mean_net_days": -0.745,
                    "mean_exc": 0.33, "ci_low": 0.3, "t_days": 2.5}
    gate = check_promotion(_rule(family="f5_supply", stats=concentrated), [_control(-0.227)])
    assert gate["eligible"]
    assert not any("평균수익 미충족" in r for r in gate["stat_reasons"])


def test_concentration_is_caught_by_significance_not_by_the_floor():
    # 쏠림이 심해 일 클러스터 t 가 문턱 미달이면 그쪽에서 걸린다(절대 하한이 아니라).
    concentrated = {"n": 23, "n_days": 12, "mean_net": 0.950, "mean_net_days": -0.745,
                    "mean_exc": 0.33, "ci_low": 0.3, "t_days": 0.4}
    gate = check_promotion(_rule(family="f5_supply", stats=concentrated), [_control(-0.227)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_control_stats_never_change_the_verdict():
    # 대조군 조건 제거(2026-08-04)의 계약 — 대조군 stats 가 어떻든 판정이 같아야 한다.
    # (구 동작에서는 이 rule 이 mean_net 0.2 < 대조군 0.5 로 탈락했다.)
    rule = _rule(stats={"n": 40, "n_days": 12, "mean_net": 0.2, "mean_net_days": 0.2,
                        "mean_exc": 0.15, "ci_low": 0.1, "t_days": 2.1})
    ctrl = {"name": "c", "family": "control", "role": "benchmark", "status": "live",
            "stats": {"mean_net": 0.5, "mean_net_days": -9.0}}
    assert check_promotion(rule, [ctrl])["eligible"]
    assert check_promotion(rule, [])["eligible"]


def test_demotion_uses_same_weighting_as_promotion():
    # 승격은 종목-일, 강등은 일 등가중이면 두 문턱 사이에 모순 구간이 생긴다.
    r = {"name": "r", "family": "f4_laggard", "role": "selector", "status": "live",
         "stats": {"recent_n": 29, "recent_n_days": 10,
                   "recent_mean_net": 0.8, "recent_mean_net_days": -0.3}}
    assert not check_demotion(r)["demote_candidate"]
    r["stats"]["recent_mean_net"] = -0.2
    assert check_demotion(r)["demote_candidate"]


# ── 승격 게이트 정책 (2026-07-28: strict / experimental) ──
# experimental 은 **일 클러스터 t 와 판정 일정만** 면제한다(2026-08-04: ci_low 는 면제에서 빼냈다).
# 평균수익>0 · 거래일≥10 · ci_low>0 · 실행 가능성은 **그대로 남는다** — 안전망이므로 면제 금지.

_WEAK_SIG = {"n": 52, "n_days": 10, "mean_net": 1.19, "mean_net_days": 0.45,
             "ci_low": 0.14, "t_days": 1.17, "mean_exc": 0.79}


def test_default_policy_is_strict_fail_safe():
    # 호출부가 policy 를 빼먹으면 엄격한 쪽으로 동작해야 한다.
    gate = check_promotion(_rule(family="f4_laggard", stats=_WEAK_SIG), [_control(-0.227)])
    assert not gate["eligible"]
    assert any("일 클러스터 t" in r for r in gate["stat_reasons"])


def test_experimental_waives_day_cluster_t_only():
    # _WEAK_SIG 는 ci_low +0.14(양수)·일 t 1.17(문턱 1.833 미달) — t 만 면제되므로 통과한다.
    gate = check_promotion(_rule(family="f4_laggard", stats=_WEAK_SIG), [_control(-0.227)],
                           policy="experimental")
    assert gate["eligible"], gate["stat_reasons"]


def test_experimental_still_requires_positive_ci_low():
    # 2026-08-04 사용자 결정 — 안정성 하한은 **정책 무관 공통**이다. 초과수익·대조군 우위를
    # 제거하자 experimental 의 실효 조건이 '10거래일 평균 양수'뿐이 되어(무엣지 통과 확률 ≈50%)
    # 과적합 방어가 월 승격 상한 하나에 걸렸다. 월 상한을 올리는 대신 이 하한을 되살렸다.
    # 실측 대상: f5_prog_pm_reversal(평균 +0.496% / ci_low -0.745%).
    unstable = {**_WEAK_SIG, "mean_net": 0.496, "mean_net_days": -0.54, "ci_low": -0.745,
                "t_days": -0.4}
    gate = check_promotion(_rule(family="f5_supply", stats=unstable), [_control(-0.227)],
                           policy="experimental")
    assert not gate["eligible"]
    assert any("신뢰구간 하한" in r for r in gate["stat_reasons"])


def test_experimental_still_requires_positive_mean_net():
    losing = {**_WEAK_SIG, "mean_net": -0.3}
    gate = check_promotion(_rule(family="f4_laggard", stats=losing), [_control(-0.5)],
                           policy="experimental")
    assert not gate["eligible"]
    assert any("평균수익 미충족" in r for r in gate["stat_reasons"])


def test_experimental_does_not_require_positive_excess():
    # 2026-08-04: 초과수익은 어느 정책에서도 게이트 조건이 아니다(상세 화면 표기 전용).
    below_universe = {**_WEAK_SIG, "mean_net": 1.5, "mean_exc": -0.2}
    gate = check_promotion(_rule(family="f4_laggard", stats=below_universe), [_control(-0.227)],
                           policy="experimental")
    assert gate["eligible"], gate["stat_reasons"]


def test_experimental_still_requires_trading_days_and_executability():
    few = {**_WEAK_SIG, "n_days": 4}
    g1 = check_promotion(_rule(family="f4_laggard", stats=few), [_control(-0.227)],
                         policy="experimental")
    assert not g1["eligible"] and any("거래일 부족" in r for r in g1["stat_reasons"])
    g2 = check_promotion(
        _rule(family="f7_risk", role="selector", stats=_WEAK_SIG,
              predicate=[{"col": "short_wght", "op": ">=", "value": 15}]),
        [_control(-0.227)], policy="experimental")
    assert not g2["eligible"] and g2["exec_reasons"]


def test_experimental_does_not_change_veto_gate():
    # veto 는 원래 유의성을 요구하지 않으므로 정책과 무관하게 동일해야 한다.
    veto = _rule(family="f7_risk", role="veto", stats=GOOD_VETO_STATS,
                 predicate=[{"col": "is_bio", "op": "==", "value": 1}])
    assert check_promotion(veto, [])["eligible"]
    assert check_promotion(veto, [], policy="experimental")["eligible"]
