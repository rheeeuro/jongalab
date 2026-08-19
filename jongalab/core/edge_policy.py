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
    # 재료 지속성 라벨 (2026-07-29 sql/40, 축·합성 v2 = 2026-08-05 sql/52) — closing_bet 이
    # 선정 시점에 OpenAI 벌크 판정으로 채우는 컬럼이라 선정 레이어에서 실행 가능하다.
    # ⚠️ 선정 시점에 채워지는 컬럼을 여기 빠뜨리면 그 컬럼을 쓰는 rule 이 `rule_layer=None`
    # (어느 레이어에서도 실행 불가)이 되어 통계 게이트를 통과해도 영구히 승격되지 않는다.
    # 반대로 컬럼을 넣는다고 live 가 되는 것도 아니다 — 통계 게이트는 그대로다.
    # 누락 사고 경위: docs/history/edge-ledger.md
    # `news_material_size_ratio` 는 LLM 이 뽑은 금액을 코드가 시총으로 나눈 파생이라 같은 시점.
    # `mat_run_ret_3d`·`mat_up_days` 는 **결과 라벨**(D+3)이므로 여기 넣지 않는다.
    "news_next_milestone", "news_milestone_horizon", "news_amount_locked",
    "news_material_size_ratio", "news_driver_scope", "news_stage",
    "news_durability", "news_durability_v",
    # 재료 신선도 (2026-08-05, sql/56) — 판정 코퍼스 최신 재료 기사의 경과 시간(h).
    # closing_bet 실행 시각 기준 파생이라 선정 레이어 값이다.
    "news_material_age_h",
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
    # 리스크 라벨 (2026-08-13, sql/64) — 값이 **T-1 확정치**다. 매수 직전 14:30 회차
    # (scheduler `after_hours_risk_pre_buy`, `--risk-only`)가 채우고, closing_bet 이 오늘 행의
    # 값을 메모리 dict 로 캐리포워드한다(뉴스 라벨과 같은 방식).
    # ⚠️ 14:30·17:50 두 회차는 **같은 값**을 쓴다 — 수집 코드가 `dt < 오늘` 행만 고르기 때문이다.
    # 채점 표본과 집행 값이 같은 변수라 과거 stats 를 그대로 승격 근거로 쓸 수 있다.
    # ah_*·exec_str 은 여기 넣지 않는다 — 그건 T-1 이 아니라 **당일 장 마감 후** 값이라
    # 선정 시점에 존재할 수 없다.
    "credit_remn_rt", "short_wght", "short_wght_5d", "lend_remn", "lend_irds_5d",
})

_MARKET_PREFIX = "market."

# 선정 시점에 쓸 수 있는 **시장 스냅샷 컬럼** (2026-08-13).
# 스냅샷은 매수 직전 14:30(scheduler `market_snapshot_pre_buy`)과 19:50(gap_check --base-nxt)
# 두 번 구워진다. **모든 축을 열면 안 된다** — 채점은 19:50 저장값으로 하는데 집행은 14:30 값을
# 보게 되어, 두 시점 값이 다른 축은 '채점 표본 ≠ 집행 값'이 된다. 그래서 판정 기준은 하나다:
#   **미국 정규장이 이미 끝나 그날 안에는 더 변하지 않는 확정치인가.**
# SOX·SPX 는 한국시간 06:00 에 마감된 값이라 14:30 에 읽든 19:50 에 읽든 같다.
# 제외: nq_fut/vix/usdkrw/wti(24시간 움직임) · kospi/kosdaq(14:30 은 장중, 19:50 은 마감) ·
#       k200f_day/night(세션 자체가 다름) · ewy/koru/skhy(미국 프리마켓~정규장) ·
#       news_*_tone(그 시점까지 라벨된 것만 세는 누적값).
SELECTION_TIME_MARKET_COLS: frozenset[str] = frozenset({"sox_ret", "spx_ret"})


def _market_col_ok(col: str) -> bool:
    """`market.` 컬럼이 선정 시점에 쓸 수 있는 축인지."""
    return col[len(_MARKET_PREFIX):] in SELECTION_TIME_MARKET_COLS


def selection_executable(predicate: list) -> tuple[bool, list[str]]:
    """predicate 가 선정 시점에 실행 가능한지. 반환: (가능 여부, 불가 컬럼 목록)."""
    missing = []
    for cond in predicate or []:
        col = cond.get("col", "") if isinstance(cond, dict) else ""
        ok = _market_col_ok(col) if col.startswith(_MARKET_PREFIX) else col in SELECTION_TIME_COLS
        if not ok:
            missing.append(col)
    return (not missing, missing)


# ── 집행 시점(NXT 19:50 데드라인) 실행 가능성 (2026-08-03) ──
# 선정 레이어 말고 **집행 레이어**에서 평가되는 rule 을 위한 두 번째 화이트리스트.
# 배경: NXT 매수는 19:50 데드라인 단일 주문이고, `signal_executor` 가 그 순간 종목마다
# NXT 현재가를 이미 조회한다(체결 참고가). 즉 **19:50 야간 갭은 주문 직전에 알 수 있다** —
# 선정 시점(13~15시·19:30 회차)엔 NULL 이라 SELECTION_TIME_COLS 에는 못 들어가지만,
# 집행기가 그 값을 채워 predicate 를 평가할 수 있다.
# 이 구분이 없으면 19:50 값을 쓰는 rule 은 통계가 아무리 강해도 영구 승격 불가가 되고, 그 가설을
# 쓰려면 원장을 우회한 하드코딩이 필요해진다(= 채점·강등 감시 소실).
# 확장 경위: docs/history/edge-ledger.md
#
# ⚠️ **집행 레이어 rule 은 종목을 추가하지 못한다 — 화이트리스트로만 동작한다.**
# 후보 풀·시드 배분이 19:30 에 이미 확정된 뒤라 빈 슬롯을 채울 대상이 없다. 그래서
# role=selector 여도 실효 의미는 "선정된 NXT 종목 중 매칭분만 매수"(reduce-only)다.
# 대가: 하이브리드 대체가 안 되므로 **거른 몫의 시드가 논다**. 그 전제로 측정해야 한다.
EXECUTION_TIME_COLS: frozenset[str] = SELECTION_TIME_COLS | frozenset({
    # 19:50 NXT 스냅샷 계열 — 집행기가 주문 직전 실시간으로 계산해 행에 덮어쓴다.
    #   nxt_gap_pct = (NXT 현재가 − KRX 확정 종가) / KRX 확정 종가 × 100
    # gap_check --base-nxt(19:50)가 사후에 같은 정의로 기록하므로 **채점 표본과 집행 값이
    # 같은 변수**다(rule 의 과거 stats 를 그대로 승격 근거로 쓸 수 있는 이유).
    "nxt_gap_pct", "nxt_price_1950", "nxt_listed",
})


def execution_executable(predicate: list) -> tuple[bool, list[str]]:
    """predicate 가 **집행 시점(NXT 19:50)** 에 실행 가능한지. 반환: (가능 여부, 불가 컬럼 목록)."""
    missing = []
    for cond in predicate or []:
        col = cond.get("col", "") if isinstance(cond, dict) else ""
        ok = _market_col_ok(col) if col.startswith(_MARKET_PREFIX) else col in EXECUTION_TIME_COLS
        if not ok:
            missing.append(col)
    return (not missing, missing)


def rule_layer(predicate: list) -> str | None:
    """이 rule 이 어느 레이어에서 동작하는가 — predicate 컬럼에서 파생(별도 컬럼 없음).

    'selection' : 선정 시점에 평가 가능 → closing_bet 의 edge_selection 이 쓴다(종목 추가 가능)
    'execution' : 선정 시점엔 불가하지만 NXT 19:50 데드라인엔 가능 → signal_executor 가
                  화이트리스트로 쓴다(종목 추가 불가, reduce-only)
    None        : 어느 레이어에서도 실행 불가(19:50 이후·익일 수집 피처) → 페이퍼 검증 전용
    선정 시점 가능한 rule 을 집행 레이어로 내리지 않는다 — 선정에서 쓰는 게 항상 낫다
    (대체가 가능해 시드가 놀지 않는다).
    """
    if selection_executable(predicate)[0]:
        return "selection"
    if execution_executable(predicate)[0]:
        return "execution"
    return None


# ── 승격 게이트 (candidate → live) ──

# 최소 거래일 수 — 같은 날 종목들의 오버나이트 수익률은 시장 무브로 강하게 상관되어,
# 종목-일 표본수(n)만으로는 광역 rule 이 갭업 며칠만에 표본을 채우고 CI 를 과신한다. 실효 표본은
# 거래일 수에 가까우므로 서로 다른 거래일이 이만큼 쌓여야 승격 검토 대상이 된다
# (하루가 평균을 통째로 뒤집은 사례: docs/history/edge-ledger.md).
PROMO_MIN_DAYS = 10

# 일 클러스터 t 문턱 — `ci_low` 는 종목-일 iid 가정이라 같은 날 종목들이 시장 무브로 상관된 만큼
# 유의성을 과신한다. 거래일을 관측 단위로 묶은 t(stats.t_days)를 selector 승격 조건에 요구한다.
# 단측 95% ≈ 1.65.
# **veto 에는 적용하지 않는다** — reduce-only 라 최악이 기회비용이고, veto 의 가치는 평균이 아니라
# 꼬리 차단에 있다. 평균 t 를 요구하면 정작 필요한 보호 veto 가 후보로도 못 올라온다.
# 도입 근거·뒤집힌 사례: docs/history/edge-ledger.md
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


# ── 판정 일정 (sql/39) — 게이트를 매일 재검사하면 무기한 재시험(optional stopping)이 된다 ──
# 그래서 **시험 횟수를 묶는다**:
#   발견(1~DISCOVERY_DAYS) 에서 통계 게이트 → 통과 시 확인창(다음 CONFIRM_DAYS)의
#   **발견에 쓰지 않은 새 표본**으로 재확인 → 확인일에 단 1회 판정.
# 대가는 검출력이고, 초과수익 채점이 그 일부를 되사온다.
# 전이는 여전히 관리자 수동 — 여기서 자동 retire 하지 않는다(판정만 기록하고 알림을 멈춘다).
# 오탐률 시뮬레이션 근거: docs/history/edge-ledger.md
DISCOVERY_DAYS = 10
CONFIRM_DAYS = 10

# 확인창 통과 기준 — 발견 단계만큼 엄격하게 요구하면 진짜 엣지도 대부분 탈락한다(검출력 붕괴).
# '새 표본에서도 평균수익이 양수'만 요구하고, 자는 발견 게이트와 같은 **절대 평균수익**이다
# (자가 다르면 판정 기록에 단위가 다른 사유가 섞여 사람이 읽을 수 없다).
CONFIRM_MIN_MEAN_NET = 0.0

# **veto 는 부호가 반대다** — 발견 게이트가 제외 종목의 원시 평균 음수(실익)를 보므로 확인창도
# 같은 자(mean_net<0)로 재확인한다. role 을 안 보면 "제외할 종목이 시장을 이겨야 확증"이라는
# 뒤집힌 판정이 되어 **잘 작동하는 veto 가 그 이유로 종결**된다.
CONFIRM_VETO_MAX_MEAN_NET = 0.0

DECISION_STAGES: tuple[str, ...] = ("discovery", "confirming", "decided")

# ── 승격 게이트 정책 — 자는 양쪽 다 절대 평균수익(mean_net) ──
# strict       : 유의성 2종(ci_low>0 + t_days≥t분포임계값) 요구 + 판정 일정 강제.
# experimental : **일 클러스터 t 와 판정 일정만** 면제. 남는 조건은 거래일≥10 · 평균수익>0 ·
#                **ci_low>0(안정성 하한)** · 실행 가능성.
# 대가·롤백은 core/config.py 의 EDGE_PROMO_POLICY 주석, 판정 경위는 docs/history/edge-ledger.md.
# **기본값은 strict** — 호출부가 정책을 넘기지 않으면 엄격한 쪽으로 동작해야 한다(fail-safe).
# 실제 운영 정책은 config.EDGE_PROMO_POLICY 이고, 라우터·평가기가 그 값을 명시로 넘긴다.
POLICIES: tuple[str, ...] = ("strict", "experimental")


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


def check_promotion(rule: dict, control_rules: list[dict], policy: str = "strict") -> dict:
    """승격 자격 판정 — 라우터(409 사유)·평가기(알림·stats.promo_eligible)가 공유하는 단일 게이트.

    rule: stats 가 최신으로 갱신된 rule dict. control_rules: role=benchmark 인 live rule 목록.
    반환: {"eligible": bool, "stat_reasons": [...], "exec_reasons": [...]}
      - stat_reasons: selector 는 **평균수익**(mean_net>0 — "돈을 버는가")·거래일 수·
        신뢰구간·**일 클러스터 t**(2026-08-04 부터 뒤 둘도 **원시(절대) 계열** ci_low·t_days —
        "우연이 아닌가"), veto 는 최소 실익 게이트(거래일 수 + 제외 종목 평균 음수) 미충족
        사유(benchmark 는 면제). **대조군 우위는 2026-08-04 게이트에서 제거**됐고
        `control_rules` 인자는 호출부 시그니처 유지를 위해 남아 있다(현재 미사용).
      - exec_reasons: 선정 시점 실행 불가 사유(benchmark 는 면제 — 선정에 안 쓰므로)
    (월 승격 상한은 2026-08-05 폐지 — "게이트를 통과하면 승격한다"가 규율이다.)
    """
    role = rule_role(rule)
    stats = rule.get("stats") or {}
    stat_reasons: list[str] = []
    exec_reasons: list[str] = []

    # 통계 게이트 — selector 는 기대값 전체 검증, benchmark 는 실탄이 아니라 기준선 교체라 면제.
    # veto 는 아래 별도의 최소 실익 게이트만 적용한다.
    if role == "selector":
        # ── 자는 **절대 평균순수익(mean_net) 하나로 통일**한다 ──
        # 게이트의 두 질문을 모두 절대 계열로 묻는다:
        #   "돈을 버는가?"   → mean_net > 0 (비용 차감 후 실현 손익의 부호)
        #   "우연이 아닌가?" → ci_low(CI 하한) · t_days(일 클러스터 t)
        # 초과 계열(mean_exc·ci_low_exc·t_days_exc)은 stats 에 계속 계산·저장되지만
        # **게이트에서는 쓰지 않고 룰 상세 화면 표기·수동 검토용 진단값**으로만 남긴다(아래
        # '대조군 우위' 주석에 그 대가와 남은 방어선을 적었다).
        # 대가(알고 택한다): 절대 계열은 같은 날 시장 무브가 분산에 그대로 남아 잡음이 초과
        # 계열의 약 2배다 → ci_low·t_days 문턱을 통과하기 더 어렵다. 지금 운영 값인
        # experimental 은 **t_days 만** 면제하므로 실효 기준은
        # **mean_net>0 + 거래일≥10 + ci_low>0 + 실행 가능성**이다.
        ci_low = stats.get("ci_low")
        n_days = stats.get("n_days") or 0
        # 절대 수익성 하한 — 비용(EDGE_COST_PCT) 차감 후 순수익이 양수여야 한다.
        # 손실 최소화가 1순위이므로 '덜 잃는 쪽'을 고르는 게 아니라 '버는 것만' 올린다.
        #
        # **효과 크기는 종목-일 가중(mean_net) — 시드 배분을 반영하지 않는다.**
        # 이유: ① rule 채점은 **유니버스 전체**에 적용된다 — 매칭된 종목-일 대부분은 애초에
        # 사지도 않은 종목이라 '그날 계좌 수익률' 개념이 성립하지 않는다. ② 시드 배분(trading
        # 도메인 SEED_MAX_NAME_PCT)은 바뀐다. 측정이 배분에 의존하면 배분을 바꿀 때마다 과거
        # 점수가 무효가 된다 — 가설 검증은 집행 방식과 분리해야 한다.
        # 참고: `mean_net_days`(일 등가중)도 stats 에 함께 있다. 둘의 격차가 크면 수익이 매칭
        # 많은 날에 쏠렸다는 신호다 → 화면·수동 검토용 진단값.
        # **유의성은 그 쏠림을 t_days(일 등가중)가 잡는다.**
        mean_net = stats.get("mean_net")
        if mean_net is None or mean_net <= 0:
            stat_reasons.append(
                f"평균수익 미충족: mean_net={mean_net}%(>0 필요) — 비용 차감 후 실제로 "
                "돈을 버는 rule 만 실탄에 올린다"
            )
        # **표본 규율은 거래일 수 + 거래일 자유도 t 문턱이 담당한다** — `min_sample`(종목-일)은
        # 게이트에서 쓰지 않는다(단위가 거래일 규율과 어긋나 하루 1~2종목만 매칭하는 좁은 룰을
        # 막았다). min_sample 컬럼은 참고값으로 남는다. 경위: docs/history/edge-ledger.md
        if n_days < PROMO_MIN_DAYS:
            stat_reasons.append(
                f"거래일 부족: n_days={n_days} < {PROMO_MIN_DAYS} — 같은 날 표본은 "
                "시장 무브로 상관되어 종목-일 n 만으로는 과신"
            )
        # ── 안정성 하한(신뢰구간) — **정책 무관 공통(experimental 도 면제되지 않는다)** ──
        # '평균이 양수'만으로는 엣지가 0인 룰도 대칭성상 절반이 통과한다. **"안정적으로 수익이
        # 나는가"를 게이트가 직접 묻는 조건**이 ci_low>0 이다(평균에서 표본 잡음을 뺀 보수적
        # 하한이 여전히 양수인가). 이게 지금 과적합 방어의 핵심이다.
        # 도입 근거·실측 효과: docs/history/edge-ledger.md
        if ci_low is None or ci_low <= 0:
            stat_reasons.append(
                f"신뢰구간 하한 미충족: ci_low={ci_low}(>0 필요) — 평균이 양수여도 흔들림이 크면 "
                "'안정적으로 버는' 게 아니다"
            )
        # ── 일 클러스터 t 는 **experimental 에서 면제** ──
        # 현행 legacy 선정 자체가 마이너스라 도전자 오탐의 기대 비용이 낮다는 판단이다. 남은
        # 안전망은 위 ci_low 하한과 강등 감지(최근 창, 최소 5거래일).
        # 실측 근거: docs/history/edge-ledger.md · docs/history/selection-scoring.md
        if policy != "experimental":
            # 일 클러스터 t — ci_low(종목-일 iid)의 과신을 거래일 단위로 교정. 문턱은 고정 1.65 가
            # 아니라 **거래일 자유도의 t 분포 임계값**을 쓴다(소표본에서 1.65 는 너무 관대 — 거래일
            # 10일이면 1.833). None(거래일 1일이라 분산 추정 불가)은 fail-closed.
            t_days = stats.get("t_days")
            t_need = day_t_threshold(n_days) or PROMO_MIN_DAY_T
            if t_days is None or t_days < t_need:
                stat_reasons.append(
                    f"일 클러스터 t 미충족: t_days={t_days}(>={t_need} 필요, 거래일 {n_days}일 "
                    "자유도 기준) — 같은 날 종목은 시장 무브로 상관되어 거래일을 관측 단위로 묶어야 "
                    "실효 유의성이 나온다"
                )
        # ── 대조군 우위·초과수익은 **게이트 조건이 아니다** ──
        # 규율은 "평균보다 수익이 크지 않더라도 안정적으로 수익이 나면 그만" — 현행 선정을 못
        # 이기더라도 그 자체로 돈을 버는 rule 이면 실탄에 올린다. 월 승격 상한도 없다.
        # ⚠️ 대가: "그 기간 장이 오른 몫"을 걸러내는 자동 장치가 게이트에 없다(상승장에 등록된
        # rule 이 유리해진다). 남은 방어선은 ① mean_net>0(비용 차감 후 실제 수익) ② 거래일≥10
        # ③ ci_low>0 ④ 강등 감시(check_demotion, 최근 창) ⑤ 승격 시 관리자 수동 승인.
        # 초과수익은 계속 계산되어 룰 상세 화면에 뜨므로 **승인 전 그 값을 눈으로 확인하는 것이
        # 이 방어선의 일부**다.
        # `control_rules` 인자는 호출부(라우터·평가기) 시그니처와 되돌릴 여지를 남기려고 유지한다.
        # 제거·폐지 경위: docs/history/edge-ledger.md

    # veto 최소 실익 게이트 — reduce-only 라 selector 급 검증(CI)은 요구하지 않지만, 완전 면제하면
    # 등록 당일 표본 몇 개로도 '승격 후보' 알림이 매일 반복된다. 거래일이 쌓이고, 제외했을 종목
    # 평균이 음수(제외가 실제로 손실을 걸러냈다는 증거)여야 후보다.
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

    # 실행 가능성 게이트 — live 는 실탄이므로 **어느 레이어에서든** 실제 동작해야 한다(benchmark 면제).
    # 선정 시점(13~15시)뿐 아니라 집행 시점(NXT 19:50)도 본다: 집행기가 주문 직전에 NXT 갭을
    # 계산해 predicate 를 평가할 수 있으므로 그 컬럼만 쓰는 rule 도 무음 no-op 이 아니다.
    if role in ("selector", "veto"):
        predicate = rule.get("predicate") or []
        if rule_layer(predicate) is None:
            _, missing = execution_executable(predicate)
            exec_reasons.append(
                # 콜론 앞부분은 화면 배지(stats.promo_blockers)로도 쓰이니 짧게 유지한다.
                f"실행 불가: {missing} — 선정 시점(13~15시)에도 NXT 집행 시점(19:50)에도 없는 "
                "컬럼입니다(19:50 이후·익일 수집). live 여도 무음 no-op 가 됩니다"
            )

    return {
        "eligible": not stat_reasons and not exec_reasons,
        "stat_reasons": stat_reasons,
        "exec_reasons": exec_reasons,
    }


def check_confirmation(confirm_stats: dict | None, role: str = "selector") -> dict:
    """확인창 판정 — 발견에 **쓰지 않은 새 표본**으로만 재확인한다.

    confirm_stats: 확인창 구간(발견 이후 CONFIRM_DAYS 거래일)만으로 재계산한 stats.
    발견 단계와 같은 강도를 요구하면 진짜 엣지도 대부분 탈락하므로(검출력 붕괴),
    '새 표본에서도 방향이 재현되는가'만 본다. 표본 부재는 fail-closed.

    **자는 양쪽 다 절대 평균수익(mean_net) 이고 부호만 반대다** — 발견 게이트(check_promotion)와
    같은 자를 쓴다(2026-08-04 selector 를 초과수익에서 절대로 통일):
      selector : mean_net > 0 (새 표본에서도 돈을 벌고 있다)
      veto     : mean_net < 0 (제외가 여전히 손실을 걸러내고 있다 — 제외 대상의 성적)
    role 기본값은 selector(구 동작) — 호출부는 rule_role(rule) 로 명시해 넘긴다.
    반환에는 `mean_exc`(초과수익)도 담지만 **판정에는 쓰지 않는다** — 화면·알림 표기용이다.
    """
    s = confirm_stats or {}
    n_days = s.get("n_days") or 0
    if role == "veto":
        mean_net = s.get("mean_net")
        if mean_net is None:
            return {"pass": False, "reasons": ["확인창 표본 없음 — 제외 종목 성적을 구할 수 없었습니다"],
                    "mean_exc": s.get("mean_exc"), "mean_net": None, "n_days": n_days}
        ok = mean_net < CONFIRM_VETO_MAX_MEAN_NET
        return {
            "pass": ok,
            "reasons": [] if ok else [
                f"확인창 실익 미재현: 제외 종목 mean_net={mean_net}"
                f"(<{CONFIRM_VETO_MAX_MEAN_NET} 필요) — 새 표본에서는 제외 대상이 손실이 아니었습니다"
            ],
            "mean_exc": s.get("mean_exc"),
            "mean_net": mean_net,
            "n_days": n_days,
        }
    mean_net = s.get("mean_net")
    if mean_net is None:
        return {"pass": False, "reasons": ["확인창 표본 없음 — 새 표본 성적을 구할 수 없었습니다"],
                "mean_exc": s.get("mean_exc"), "mean_net": None, "n_days": n_days}
    ok = mean_net > CONFIRM_MIN_MEAN_NET
    return {
        "pass": ok,
        "reasons": [] if ok else [
            f"확인창 평균수익 미달: mean_net={mean_net}(>{CONFIRM_MIN_MEAN_NET} 필요) — "
            "발견 단계 성적이 새 표본에서 재현되지 않았습니다"
        ],
        "mean_exc": s.get("mean_exc"),   # 표기용(판정 무관)
        "mean_net": mean_net,
        "n_days": n_days,
    }


# ── 강등 게이트 (live → retired) ──
# 최근 창(rule_evaluator._RECENT_DAYS 거래일) 표본의 최소 요건. 종목-일 표본만 보면 하루
# 시장 무브가 창을 통째로 뒤집는 오탐 강등이 난다(사례: docs/history/edge-ledger.md).
# 판정 자는 recent_alpha(시장 회귀 잔차) — 이유는 check_demotion docstring.
DEMOTE_MIN_N = 20
DEMOTE_MIN_DAYS = 5


def check_demotion(rule: dict) -> dict:
    """강등 검토 대상 판정 — 평가기 알림이 쓰는 단일 게이트.

    ── 자는 **시장 회귀 잔차 `recent_alpha`** 다(절대 수익도, 초과수익도 아니다) ──
    강등이 물어야 하는 건 "엣지가 사라졌는가"이고, 그러려면 성적에서 **그 기간 장이 움직인
    몫**을 빼야 한다. 후보였던 자 셋 중 앞 둘은 각각 반대 방향으로 틀린다:
      · 절대 `recent_mean_net`: 시장과 동기화된다. 하락 구간엔 멀쩡한 룰까지 한꺼번에 후보로
        올리고, 상승 구간엔 성적이 나쁜 룰도 하나도 못 거른다(강등 감시가 무력해진다).
      · 초과 `mean_exc`: `룰 - 시장` 이라 **beta=1 을 강제**한다. 시장을 덜 따라가는(저beta)
        방어형 룰 — 상승장엔 덜 벌어도 하락장엔 버티는 룰 — 이 상승장에서 구조적으로 음수가
        되어 부당하게 죽는다. 목표가 "잃지 않고 꾸준히"인 이상 그건 지켜야 할 룰이다.
    `alpha`(=`룰 - beta x 시장`)는 beta 를 추정해 빼므로 둘 다 피한다. 산출은
    `workers/rule_evaluator._market_fit` — beta 는 누적 표본, alpha 만 최근 창에서 다시 잡는다.
    근거·실측: docs/history/edge-ledger.md

    **역할별로 alpha 의 부호 의미가 반대다**:
      - selector: 매수한 종목의 시장 조정 수익 → 음수면 시장 몫을 빼고 나면 잃는 중 = 강등 검토
      - veto    : **제외한** 종목의 시장 조정 수익 → 양수면 이기는 종목을 버리는 중 = 강등 검토
                  (음수는 veto 가 손실을 제대로 걸러냈다는 뜻 — check_promotion 의 승격 조건과
                  같은 방향이다. 부호를 selector 와 공유하면 잘 작동하는 veto 를 매일 강등
                  후보로 올린다: veto_bio_kosdaq 이 recent_mean_net=-0.158 로 오탐 알림.)
      - benchmark: 강등 감시 제외 — 실탄이 아닌 페이퍼 기준선이라 유지 비용이 없고, 성적이
                  나쁜 것 자체가 정보다(현행 선정이 얼마나 나쁜지가 대조군의 존재 이유).
                  (2026-08-04 까지는 '대조군이 사라지면 승격 게이트가 fail-closed 로 전 후보를
                  막는다'가 추가 이유였는데, 대조군 우위 조건이 제거되어 더는 해당하지 않는다.)
    반환: {"demote_candidate": bool, "reasons": [...]} (reasons 는 해당 시 사람이 읽을 사유)
    """
    sig = demotion_signal(rule)
    if not sig["measurable"] or not sig["negative"]:
        return {"demote_candidate": False, "reasons": []}
    return {"demote_candidate": True, "reasons": [sig["reason"]]}


def demotion_signal(rule: dict) -> dict:
    """강등 신호를 **3-상태**로 판정 — 자동 전이(live↔paused)가 쓰는 원자 함수.

    `check_demotion` 의 bool 로는 "성적이 괜찮다"와 "판정할 표본이 없다"가 구분되지 않는다.
    전이는 양방향이라 이 구분이 필수다 — 표본 미충족을 '괜찮다'로 읽으면 갓 승격한 룰이
    복귀 신호를 쌓아 올린다(무근거 전이). 그래서 measurable 을 따로 낸다.

    반환: {"measurable": bool, "negative": bool, "reason": str, "alpha": float|None}
      measurable=False → 그날은 **아무 것도 세지 않는다**(상태·연속 카운트 모두 유지).
    """
    role = rule_role(rule)
    if role not in ("selector", "veto"):
        return {"measurable": False, "negative": False,
                "reason": "benchmark 는 강등 감시 대상이 아닙니다", "alpha": None}

    stats = rule.get("stats") or {}
    n = stats.get("recent_n") or 0
    n_days = stats.get("recent_n_days") or 0
    # ⚠️ recent_alpha 는 초과 기준선(유니버스 자기제외 평균)이 있어야 산출된다 — 없으면 None 이고
    # 그때는 **판정 불가**로 둔다(fail-closed). 판정 불가를 '문제 있음'으로 읽는 쪽이 더 위험하다.
    # 기준선 로드 실패는 rule_evaluator 가 경고 로그로 남긴다.
    # 창은 적응형(rule_evaluator._recent_window)이라 표본이 있는 한 n 은 자연히 이 문턱을
    # 채우고, 못 채우면 그 룰은 아직 판정할 표본이 없다는 뜻이다.
    alpha = stats.get("recent_alpha")
    if n < DEMOTE_MIN_N or n_days < DEMOTE_MIN_DAYS or alpha is None:
        return {"measurable": False, "negative": False,
                "reason": f"판정 표본 미달(n={n}/{DEMOTE_MIN_N}, 거래일={n_days}/{DEMOTE_MIN_DAYS})",
                "alpha": alpha}

    if role == "selector":
        neg = alpha < 0
        reason = f"최근 {n_days}거래일 매수 종목 시장조정수익(alpha) {alpha}% < 0"
    else:
        neg = alpha > 0
        reason = (f"최근 {n_days}거래일 제외 종목 시장조정수익(alpha) {alpha}% > 0 — "
                  "veto 가 이기는 종목을 버리는 중")
    return {"measurable": True, "negative": neg,
            "reason": reason if neg else "최근 창 alpha 부호 정상", "alpha": alpha}


# ── 운용 전이 (live ↔ paused) — 자동, 사람 승인 없음 ──
# 원장(candidate→live/retired)과 **다른 축**이다. paused 는 '표를 안 준다'일 뿐 판정이 아니라
# 되돌릴 수 있고, 그래서 자동으로 굴려도 된다. retired 는 여전히 사람만 결정한다.
#
# 연속 요구(TRANSITION_STREAK)의 단위는 **표본일**이지 달력 평일이 아니다. 표본이 없는 날은
# alpha 가 갱신되지 않으므로 달력으로 세면 같은 값이 두 번 세어져 새 정보 없이 상태가 바뀐다.
# 판정 일정(_slice_sample_days)이 이미 같은 원칙을 쓴다.
#
# 2 는 하루짜리 깜빡임을 걸러내면서 반응 속도는 유지하는 값이다(근거: docs/history/edge-ledger.md).
TRANSITION_STREAK = 2


def decide_transition(rule: dict, streak: int) -> dict:
    """live ↔ paused 자동 전이 판정. rule_evaluator 가 표본일마다 1회 호출한다.

    streak: **현재 상태를 바꾸자는 신호**가 연속 몇 표본일 나왔는가(이전 실행의 누적).
            같은 방향 신호가 오면 +1, 반대 신호가 오면 0 으로 리셋한다.

    반환: {"next_status": str|None, "streak": int, "reason": str, "measurable": bool}
      next_status=None → 전이 없음(streak 만 갱신).
    """
    status = rule.get("status")
    if status not in ("live", "paused"):
        return {"next_status": None, "streak": 0, "reason": "", "measurable": False}

    sig = demotion_signal(rule)
    if not sig["measurable"]:
        # 표본 미충족 — 상태도 카운트도 건드리지 않는다(fail-open: 갓 승격한 룰은 live 유지).
        return {"next_status": None, "streak": streak, "reason": sig["reason"],
                "measurable": False}

    # live 면 '음의 신호'가, paused 면 '정상 신호'가 상태를 바꾸자는 쪽이다.
    wants_change = sig["negative"] if status == "live" else not sig["negative"]
    streak = streak + 1 if wants_change else 0
    if streak < TRANSITION_STREAK:
        return {"next_status": None, "streak": streak, "reason": sig["reason"],
                "measurable": True}

    nxt = "paused" if status == "live" else "live"
    return {"next_status": nxt, "streak": 0, "measurable": True,
            "reason": (f"{sig['reason']} — {TRANSITION_STREAK}표본일 연속"
                       if nxt == "paused"
                       else f"{TRANSITION_STREAK}표본일 연속 정상(alpha {sig['alpha']}%) — 복귀")}
