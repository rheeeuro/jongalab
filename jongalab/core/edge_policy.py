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
    "f8_value", "f9_disc", "control",
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
    # 재무 파생 비율 (2026-07-22, sql/34) — 영업이익÷시총, closing_bet 선정 시점 파생
    "op_earnings_yield",
    # 호가 미시구조 스냅샷 (2026-07-22, sql/33) — ka10004 선정 시점 수집. 연속장 중만 유효.
    "ob_imbalance", "ob_fpr_imbalance", "ob_spread_pct",
    # DART 공시 사건 라벨 (2026-07-28, sql/36) — disclosure_collector(30분 주기)가 적재한
    # stock_event 를 closing_bet 선정 시점에 집계. 매 실행 재계산이라 저녁 재실행(19:00)에는
    # 장 마감 후 공시(15:30~18:00)까지 반영된다 → NXT 매수(19:30) 직전 veto 가 실제로 동작.
    "disc_count", "disc_bad_type", "disc_good_type",
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

# 일 클러스터 t 문턱 (2026-07-28) — `ci_low` 는 종목-일 iid 가정이라 같은 날 종목들이 시장
# 무브로 상관된 만큼 유의성을 과신한다. PROMO_MIN_DAYS 는 문턱만 세우고 CI 는 그대로 iid 였다.
# 거래일을 관측 단위로 묶은 t(stats.t_days_exc)를 selector 승격 조건에 추가한다. 단측 95% ≈ 1.65.
# 이 게이트 없이 후보로 올라와 재계산에서 뒤집힌 사례 2건:
#   f5_prog_persistent(7/27) iid t=1.82 → 일 t=0.47 / f4_sector_follower(7/28) 1.99 → 0.37.
# **veto 에는 적용하지 않는다** — reduce-only 라 최악이 기회비용이고, veto 의 가치는 평균이 아니라
# 꼬리 차단에 있다(veto_bio_kosdaq 은 대체효과 t=0.95 로 평균 유의성이 없는데도 HLB 하한가
# 꼬리 때문에 유지가 맞았다). 평균 t 를 요구하면 정작 필요한 보호 veto 가 후보로도 못 올라온다.
PROMO_MIN_DAY_T = 1.65

# 단측 95% t 임계값 (자유도 → 임계값). 거래일 표본이 작을 때 정규 근사 1.65 는 **너무 관대**하다
# (거래일 5일=df4 면 실제 임계값 2.13). 소표본에서 오히려 엄격해지도록 t 분포를 쓴다.
# df 가 표에 없으면 그보다 큰 첫 항목(=더 보수적인 값)을 쓰고, 120 초과는 정규 극한 1.645.
_T_CRIT_ONE_SIDED_95: dict[int, float] = {
    1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860,
    9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782, 13: 1.771, 14: 1.761, 15: 1.753,
    16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729, 20: 1.725, 25: 1.708, 30: 1.697,
    40: 1.684, 60: 1.671, 120: 1.658,
}


def day_t_threshold(n_days: int) -> float | None:
    """거래일 n_days 표본에 적용할 일 클러스터 t 문턱. n_days<2 면 검정 불가(None)."""
    df = (n_days or 0) - 1
    if df < 1:
        return None
    for k in sorted(_T_CRIT_ONE_SIDED_95):
        if df <= k:
            return _T_CRIT_ONE_SIDED_95[k]
    return 1.645


# ── 판정 일정 (2026-07-28) — '매일 재평가'가 게이트를 무력화하는 문제의 해법 ──
# 게이트를 매 평일 다시 검사하면 룰 하나가 무기한 재시험을 치게 된다(optional stopping).
# 시뮬레이션(일간 초과 sd 2.43): 진짜 엣지 0 인 룰의 오탐이 명목 5% → **22%**, candidate 24종이면
# 기대 오탐 5.2건·최소 1건 발생 확률 99.8%. 롤링 창은 해법이 아니라 악화다(창 크기가 고정이라
# W일마다 새 시험 → 250거래일 오탐 91%). 해법은 **시험 횟수를 묶는 것**:
#   발견(1~DISCOVERY_DAYS) 에서 통계 게이트 → 통과 시 확인창(다음 CONFIRM_DAYS)의
#   **발견에 쓰지 않은 새 표본**으로 재확인 → 확인일에 단 1회 판정.
# 오탐 22% → 2.4%. 검출력은 떨어지지만(+1%/일 88%→32%) 초과수익 채점이 손실의 절반을 되사온다.
# 전이는 여전히 관리자 수동 — 여기서 자동 retire 하지 않는다(판정만 기록하고 알림을 멈춘다).
DISCOVERY_DAYS = 10
CONFIRM_DAYS = 10

# 확인창 통과 기준 — 발견 단계만큼 엄격하게 요구하면 진짜 엣지도 대부분 탈락한다(검출력 붕괴).
# '새 표본에서도 초과수익이 양수'만 요구한다. 이 조합이 오탐 2.4%·검출력 32%(+1%/일)다.
CONFIRM_MIN_MEAN_EXC = 0.0

DECISION_STAGES: tuple[str, ...] = ("discovery", "confirming", "decided")


def decision_stage(rule: dict) -> str:
    """rule 이 판정 일정상 어느 단계인가 — decision 컬럼(기록)만 보고 판단한다.

    discovery  : 아직 발견 판정 전
    confirming : 발견 통과, 확인창 판정 대기
    decided    : 판정 완료(통과/탈락 모두) — 다시 검사하지 않는다(재시험 금지)
    """
    d = rule.get("decision") or {}
    if d.get("decided_at"):
        return "decided"
    if d.get("discovery", {}).get("pass"):
        return "confirming"
    if d.get("discovery"):
        return "decided"   # 발견에서 탈락 = 종결
    return "discovery"


def decision_due(rule: dict, n_days: int) -> str | None:
    """지금 판정해야 하는가. 반환: 'discovery' | 'confirm' | None(대기/종결).

    n_days 는 라벨 표본이 있는 누적 거래일 수(stats.n_days). 판정 시점을 **거래일 수**로
    잡는 이유: 달력일로 잡으면 매칭이 드문 rule 은 표본 없이 판정일이 지나간다.
    """
    stage = decision_stage(rule)
    if stage == "discovery" and n_days >= DISCOVERY_DAYS:
        return "discovery"
    if stage == "confirming" and n_days >= DISCOVERY_DAYS + CONFIRM_DAYS:
        return "confirm"
    return None


def check_promotion(rule: dict, control_rules: list[dict]) -> dict:
    """승격 자격 판정 — 라우터(409 사유)·평가기(알림·stats.promo_eligible)가 공유하는 단일 게이트.

    rule: stats 가 최신으로 갱신된 rule dict. control_rules: role=benchmark 인 live rule 목록.
    반환: {"eligible": bool, "stat_reasons": [...], "exec_reasons": [...]}
      - stat_reasons: selector 는 **절대 수익성**(원시 mean_net>0 — "돈을 버는가")·거래일 수·
        신뢰구간·**일 클러스터 t**(뒤 둘은 유니버스 자기제외 **초과** 계열 — "우연이 아닌가")·
        **대조군 우위**(원시 — "현행보다 나은가"), veto 는 최소 실익 게이트(거래일 수 +
        제외 종목 원시 평균 음수) 미충족 사유(benchmark 는 면제)
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
        # 두 질문에 자가 각각 따로 붙는다(2026-07-28) —
        #   "돈을 버는가?"   → **절대** 순수익 mean_net > 0 (실현 손익은 절대값이다)
        #   "우연이 아닌가?" → **초과** 계열 ci_low_exc·t_days_exc (같은 날 시장 무브를 걷어내야
        #                      잡음이 절반이 되고 다른 룰·현행과의 비교가 성립한다)
        # 하나만 쓰면 각각 다른 구멍이 난다:
        #   초과만 → 유니버스보다 낫지만 **돈은 잃는** 룰이 통과(실측: f5_late_day_strength
        #            절대 -0.39%/초과 +0.20%, f8_op_earnings_yield -0.76%/+0.15%).
        #            대조군 우위만으론 막히지 않는다 — 대조군 자체가 -0.227% 라 문턱이 음수다.
        #   절대만 → 그 기간 장이 오른 몫을 실력으로 착각(실측: 이 유니버스 기간 평균 +0.320%,
        #            양수일 7/14). 게다가 절대 계열은 잡음이 2배라 유의성에 도달하지 못한다.
        ci_low = stats.get("ci_low_exc")
        mean_net = stats.get("mean_net")
        n_days = stats.get("n_days") or 0
        # 절대 수익성 하한 — 비용(EDGE_COST_PCT) 차감 후 순수익이 양수여야 한다.
        # 손실 최소화가 1순위이므로 '덜 잃는 쪽'을 고르는 게 아니라 '버는 것만' 올린다.
        if mean_net is None or mean_net <= 0:
            stat_reasons.append(
                f"절대 수익성 미충족: mean_net={mean_net}%(>0 필요) — 비용 차감 후 실제로 "
                "돈을 버는 rule 만 실탄에 올린다(초과수익이 양수여도 절대 손실이면 제외)"
            )
        # **min_sample(종목-일)은 게이트에서 뺐다**(2026-07-28, 항목 ③). 이 프로젝트는 이미
        # "실효 표본은 거래일"이라고 결론냈는데(PROMO_MIN_DAYS·t_days) min_sample 만 종목-일
        # 단위로 남아 단위가 어긋났고, 그 결과 **통계적으로 가장 강한 좁은 룰들을 막고 있었다**
        # (f5_breakout_structure t=2.08·n=4, f4_theme_follower t=2.76·n=6 — 하루 1~2종목만
        # 매칭하는 룰은 n=40 을 채우려면 30거래일 이상 걸린다). 표본 규율은 아래 거래일 수 +
        # 거래일 자유도를 반영한 t 문턱이 담당한다. min_sample 컬럼은 참고값으로 남긴다.
        if n_days < PROMO_MIN_DAYS:
            stat_reasons.append(
                f"거래일 부족: n_days={n_days} < {PROMO_MIN_DAYS} — 같은 날 표본은 "
                "시장 무브로 상관되어 종목-일 n 만으로는 과신"
            )
        if ci_low is None or ci_low <= 0:
            stat_reasons.append(f"신뢰구간 하한 미충족: ci_low_exc={ci_low}(>0 필요)")
        # 일 클러스터 t — ci_low(종목-일 iid)의 과신을 거래일 단위로 교정. 문턱은 고정 1.65 가
        # 아니라 **거래일 자유도의 t 분포 임계값**을 쓴다(소표본에서 1.65 는 너무 관대 — 거래일
        # 10일이면 1.833). None(분산 추정 불가·초과 표본 부재)은 fail-closed.
        t_days = stats.get("t_days_exc")
        t_need = day_t_threshold(n_days) or PROMO_MIN_DAY_T
        if t_days is None or t_days < t_need:
            stat_reasons.append(
                f"일 클러스터 t 미충족: t_days_exc={t_days}(>={t_need} 필요, 거래일 {n_days}일 "
                "자유도 기준) — 같은 날 종목은 시장 무브로 상관되어 거래일을 관측 단위로 묶어야 "
                "실효 유의성이 나온다"
            )
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


def check_confirmation(confirm_stats: dict | None) -> dict:
    """확인창 판정 — 발견에 **쓰지 않은 새 표본**으로만 재확인한다.

    confirm_stats: 확인창 구간(발견 이후 CONFIRM_DAYS 거래일)만으로 재계산한 stats.
    발견 단계와 같은 강도를 요구하면 진짜 엣지도 대부분 탈락하므로(검출력 붕괴),
    '새 표본에서도 초과수익이 양수'만 본다. 표본 부재는 fail-closed.
    """
    s = confirm_stats or {}
    mean_exc = s.get("mean_exc")
    if mean_exc is None:
        return {"pass": False, "reasons": ["확인창 초과 표본 없음 — 기준선을 구할 수 없었습니다"],
                "mean_exc": None, "n_days": s.get("n_days") or 0}
    ok = mean_exc > CONFIRM_MIN_MEAN_EXC
    return {
        "pass": ok,
        "reasons": [] if ok else [
            f"확인창 초과수익 미달: mean_exc={mean_exc}(>{CONFIRM_MIN_MEAN_EXC} 필요) — "
            "발견 단계 성적이 새 표본에서 재현되지 않았습니다"
        ],
        "mean_exc": mean_exc,
        "n_days": s.get("n_days") or 0,
    }


# ── 강등 게이트 (live → retired) ──
# 최근 창(rule_evaluator._RECENT_DAYS 거래일) 표본의 최소 요건. 종목-일 표본만 보면 하루
# 시장 무브가 창을 통째로 뒤집는 오탐 강등이 난다(2026-07-20 control_legacy_top10 사례).
DEMOTE_MIN_N = 20
DEMOTE_MIN_DAYS = 5


def check_demotion(rule: dict) -> dict:
    """강등 검토 대상 판정 — 평가기 알림이 쓰는 단일 게이트.

    **역할별로 mean_net 의 부호 의미가 반대다**(2026-07-28 오탐 수정):
      - selector: 매수한 종목의 순수익 → 음수면 돈을 잃는 중 = 강등 검토
      - veto    : **제외한** 종목의 순수익 → 양수면 이기는 종목을 버리는 중 = 강등 검토
                  (음수는 veto 가 손실을 제대로 걸러냈다는 뜻 — check_promotion 의 승격 조건과
                  같은 방향이다. 부호를 selector 와 공유하면 잘 작동하는 veto 를 매일 강등
                  후보로 올린다: veto_bio_kosdaq 이 recent_mean_net=-0.158 로 오탐 알림.)
      - benchmark: 강등 감시 제외 — 페이퍼 기준선이라 유지 비용이 없고, live 대조군이 사라지면
                  check_promotion 의 '대조군 우위'가 fail-closed 로 전 후보를 막는다.
    반환: {"demote_candidate": bool, "reasons": [...]} (reasons 는 해당 시 사람이 읽을 사유)
    """
    role = rule_role(rule)
    if role not in ("selector", "veto"):
        return {"demote_candidate": False, "reasons": []}

    stats = rule.get("stats") or {}
    n = stats.get("recent_n") or 0
    n_days = stats.get("recent_n_days") or 0
    mean_net = stats.get("recent_mean_net")
    if n < DEMOTE_MIN_N or n_days < DEMOTE_MIN_DAYS or mean_net is None:
        return {"demote_candidate": False, "reasons": []}

    if role == "selector" and mean_net < 0:
        return {"demote_candidate": True,
                "reasons": [f"최근 {n_days}거래일 매수 종목 평균순수익 {mean_net}% < 0"]}
    if role == "veto" and mean_net > 0:
        return {"demote_candidate": True,
                "reasons": [f"최근 {n_days}거래일 제외 종목 평균순수익 {mean_net}% > 0 — "
                            "veto 가 이기는 종목을 버리는 중"]}
    return {"demote_candidate": False, "reasons": []}
