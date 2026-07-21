"""Edge Ledger 정책 — rule 역할·선정 시점 실행 가능성·승격 게이트의 **단일 소스**.

라우터(routers/edge_rule)·평가기(workers/rule_evaluator)·선정(workers/closing_bet)·
프론트(stats.promo_eligible 렌더링)가 전부 여기서 파생한다. 조건을 바꿀 땐 이 파일만 고친다
(부분집합이 3곳에 흩어져 서로 어긋나는 드리프트 방지).

순수 로직(DB·네트워크 무의존) → tests/test_edge_policy.py 가 계약을 고정한다.
"""

# ── rule 역할(role) — family(도메인)와 직교하는 명시 속성 (2026-07-09 분리) ──
# selector  : live 시 hybrid/rules 모드에서 매수 후보를 '선정'한다
# veto      : live 시 전 모드에서 선정 직전 '제외'만 한다(reduce-only)
# benchmark : 선정에 쓰지 않는 페이퍼 기준선·측정 도구(대조군, 수급 밴드 등) — selector 로
#             넣으면 rules 모드의 '무거래' 의미가 깨진다(예: selected==1 이 늘 top-N 을 매칭)
ROLES: tuple[str, ...] = ("selector", "veto", "benchmark")

# 도메인(family) — 가설이 어떤 데이터 축을 보는가. 역할과 독립(예: 수급 도메인의 veto).
FAMILIES: tuple[str, ...] = (
    "f1_news", "f2_global", "f3_nxt", "f4_laggard", "f5_supply", "f6_ah", "f7_risk",
    "control",
)

# 구 체계 폴백 — role 컬럼 도입(sql/15) 전에는 family 가 역할을 겸했다. 마이그레이션 전
# 배포·구 dict 에서도 안전하게 동작하도록 rule_role() 이 이 매핑으로 폴백한다.
_LEGACY_FAMILY_ROLES: dict[str, str] = {
    "f1_news": "selector", "f2_global": "selector", "f3_nxt": "selector",
    "f4_laggard": "selector", "f5_supply": "selector", "f6_ah": "selector",
    "control": "benchmark", "veto": "veto",
}


def rule_role(rule: dict) -> str | None:
    """rule 의 역할. 명시 role 컬럼 우선, 없으면(구 스키마) family 겸용 매핑으로 폴백."""
    role = rule.get("role")
    if role in ROLES:
        return role
    return _LEGACY_FAMILY_ROLES.get(rule.get("family", ""))


# ── 선정 시점(closing_bet 13~15시) 실행 가능성 ──
# closing_bet 이 select_signals 에 넘기는 reports dict 에 실제로 존재하는 predicate 대상 컬럼.
# 19:50 수집(NXT 스냅샷·market_snapshot)·익일 수집(결과 라벨) 피처는 선정 시점에 아직 없어
# NULL→매칭실패가 되므로, 그 피처를 쓰는 rule 은 live 여도 선정/veto 에서 영원히 무음 no-op 다.
# → live(실탄) 승격은 이 목록 안의 컬럼만 쓰는 rule 에만 허용한다(benchmark 제외).
# 선정 시점을 19:50 이후로 옮기는 등 집행 설계가 바뀌면 이 목록에 해당 컬럼을 추가한다.
SELECTION_TIME_COLS: frozenset[str] = frozenset({
    "stock_code", "stock_name", "sector",
    "current_price", "change_pct", "trading_value", "market_cap",
    "supply_score", "inst_net_buy", "frgn_net_buy", "indv_net_buy", "prog_net_buy",
    "supply_days", "ma_aligned", "near_high", "is_leader", "is_theme_stock",
    "content_score",
    "news_count", "news_unique_count", "news_pm_count", "news_first_today",
    "news_prior_avg", "news_sentiment", "news_catalyst",
    "score", "rank_no", "selected",
    "sector_rel_ret", "sector_leader_chg",
    # F5 수급 구조·테마 피처 (2026-07-05) — closing_bet 선정 시점 수집
    "foreign_brokers_buying", "afternoon_ret", "vol_ratio", "prog_buy_days",
    "first_seen", "theme_strength", "frgn_exhaust_rate", "frgn_exhaust_chg",
    # F7 종목 리스크 속성 (2026-07-10) — 선정 시점 파생(edge_features.is_bio)·ka10100 캡처
    "is_bio", "market",
    # 차트 구조 피처 (2026-07-19) — 일봉(기수집)·현재가 파생, 선정 시점 계산
    "dist_prior_high_pct", "round_dist_pct", "ma5_reclaim",
    # 외인 서지 후 눌림/지속 축 (2026-07-19, sql/23·24) — supply_history·일봉(기수집) 파생
    "days_since_frgn_surge", "red_candle", "red_candle_streak",
    # 매물대 볼륨프로파일 (2026-07-19, sql/25) — 일봉(기수집) 파생, rule 은 레벨 축 판정 후
    "overhead_vol_ratio", "poc_dist_pct",
    # 프로그램 장중 오전/오후 분해 (2026-07-19, sql/26) — ka90008 선정 시점 수집
    "prog_am_net", "prog_pm_net",
    # 재무 스냅샷 (2026-07-22, sql/32) — ka10001 선정 시점 수집(추가 콜 없음). 분기 저속 데이터.
    "fin_per", "fin_pbr", "fin_ev", "fin_roe", "fin_eps", "fin_bps",
    "fin_sales", "fin_op_profit", "fin_net_income",
})

_MARKET_PREFIX = "market."


def selection_executable(predicate: list) -> tuple[bool, list[str]]:
    """predicate 가 선정 시점에 실행 가능한지. 반환: (가능 여부, 불가 컬럼 목록)."""
    missing = []
    for cond in predicate or []:
        col = cond.get("col", "") if isinstance(cond, dict) else ""
        if col.startswith(_MARKET_PREFIX) or col not in SELECTION_TIME_COLS:
            missing.append(col)
    return (not missing, missing)


# ── 승격 게이트 (candidate → live) ──

# 최소 거래일 수 — 같은 날 종목들의 오버나이트 수익률은 시장 무브로 강하게 상관되어,
# 종목-일 표본수(n)만으로는 광역 rule 이 갭업 며칠만에 min_sample 을 채우고 CI 를 과신한다
# (f5_supply_band_d 사례: 2거래일 n=70, 하루가 평균을 통째로 뒤집음). 실효 표본은 거래일 수에
# 가까우므로 서로 다른 거래일이 이만큼 쌓여야 승격 검토 대상이 된다.
PROMO_MIN_DAYS = 10


def check_promotion(rule: dict, control_rules: list[dict]) -> dict:
    """승격 자격 판정 — 라우터(409 사유)·평가기(알림·stats.promo_eligible)가 공유하는 단일 게이트.

    rule: stats 가 최신으로 갱신된 rule dict. control_rules: role=benchmark 인 live rule 목록.
    반환: {"eligible": bool, "stat_reasons": [...], "exec_reasons": [...]}
      - stat_reasons: selector 는 표본·신뢰구간·대조군 우위, veto 는 최소 실익 게이트
        (거래일 수 + 제외 종목 평균 음수) 미충족 사유(benchmark 는 면제)
      - exec_reasons: 선정 시점 실행 불가 사유(benchmark 는 면제 — 선정에 안 쓰므로)
    월 승격 상한은 시점 의존 운영 제약이라 여기 넣지 않고 라우터가 별도 검사한다.
    """
    role = rule_role(rule)
    stats = rule.get("stats") or {}
    stat_reasons: list[str] = []
    exec_reasons: list[str] = []

    # 통계 게이트 — selector 는 기대값 전체 검증, benchmark 는 실탄이 아니라 기준선 교체라 면제.
    # veto 는 아래 별도의 최소 실익 게이트만 적용한다.
    if role == "selector":
        n = stats.get("n") or 0
        ci_low = stats.get("ci_low")
        mean_net = stats.get("mean_net")
        min_sample = rule.get("min_sample") or 0
        if n < min_sample:
            stat_reasons.append(f"표본 부족: n={n} < min_sample={min_sample}")
        n_days = stats.get("n_days") or 0
        if n_days < PROMO_MIN_DAYS:
            stat_reasons.append(
                f"거래일 부족: n_days={n_days} < {PROMO_MIN_DAYS} — 같은 날 표본은 "
                "시장 무브로 상관되어 종목-일 n 만으로는 과신"
            )
        if ci_low is None or ci_low <= 0:
            stat_reasons.append(f"신뢰구간 하한 미충족: ci_low={ci_low}(>0 필요)")
        # 대조군 우위 — live benchmark 의 mean_net 최대값 이상. 대조군이 없거나 미평가면
        # fail-closed(승격 불가): '대조군 우위' 규율이 조용히 증발하는 fail-open 을 막는다.
        control_means = [
            (c.get("stats") or {}).get("mean_net")
            for c in control_rules
            if (c.get("stats") or {}).get("mean_net") is not None
        ]
        if not control_means:
            stat_reasons.append("대조군 부재/미평가: live control rule 의 stats.mean_net 이 없습니다")
        elif mean_net is None or mean_net < max(control_means):
            stat_reasons.append(
                f"대조군 우위 미충족: mean_net={mean_net} < control 최고={max(control_means)}"
            )

    # veto 최소 실익 게이트 — reduce-only 라 selector 급 검증(CI·대조군)은 요구하지 않지만,
    # 완전 면제하면 등록 당일 표본 몇 개로도 '승격 후보' 알림이 매일 반복된다
    # (2026-07-13 veto_bio 사례: 1거래일 n=3, 제외 종목 평균 +0.01%인데 eligible).
    # 거래일이 쌓이고, 제외했을 종목 평균이 음수(제외가 실제로 손실을 걸러냈다는 증거)여야 후보.
    elif role == "veto":
        n_days = stats.get("n_days") or 0
        if n_days < PROMO_MIN_DAYS:
            stat_reasons.append(
                f"거래일 부족: n_days={n_days} < {PROMO_MIN_DAYS} — veto 도 실익을 재려면 "
                "제외 표본이 여러 거래일 쌓여야 합니다"
            )
        mean_net = stats.get("mean_net")
        if mean_net is None or mean_net >= 0:
            stat_reasons.append(
                f"실익 미입증: 제외 종목 평균순수익 mean_net={mean_net}(<0 필요 — "
                "제외 대상이 평균적으로 손실이어야 veto 이득)"
            )

    # 실행 가능성 게이트 — live 는 실탄이므로 선정 시점에 실제 동작해야 한다(benchmark 면제).
    if role in ("selector", "veto"):
        ok, missing = selection_executable(rule.get("predicate") or [])
        if not ok:
            exec_reasons.append(
                f"선정 시점(13~15시) 실행 불가 피처 사용: {missing} — 19:50/익일 수집 컬럼은 "
                "선정 때 NULL 이라 live 여도 무음 no-op 가 됩니다(집행 설계 변경 후 승격)"
            )

    return {
        "eligible": not stat_reasons and not exec_reasons,
        "stat_reasons": stat_reasons,
        "exec_reasons": exec_reasons,
    }
