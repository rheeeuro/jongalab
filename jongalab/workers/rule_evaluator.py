"""rule_evaluator — Edge Ledger 일별 채점 워커 (평일 09:40, outcome_backfill 09:30 이후).

학습 루프의 심장: 활성 가설(rule)을 유니버스 전체에 매일 적용해 페이퍼 성적을 누적한다.
매매 집행은 하지 않는다(Phase 4). 순수 관측·평가 레이어.

[동작 — 2-pass]
  pass 1 (채점): rule × 날짜 catch-up — daily_stock_report 의 과거 report_date 중 아직
     edge_rule_daily 에 없는 날짜를 predicate 매칭(row + market_snapshot 조인) →
     exit_label 값 수집 → mean_net = mean(label) − EDGE_COST_PCT → edge_rule_daily upsert.
     결과 라벨 미도래 날짜는 스킵(다음날 재시도)하되, 등록 후 _LABEL_RETRY_DEADLINE_DAYS 를
     넘긴 날짜는 n=0 sentinel 로 종결한다(실시간 라벨은 소급 불가 — 영구 재시도 방지).
     이어서 rule 별 누적 통계(registered_at 이후 표본만, 사전 등록 원칙) 재계산.
  pass 2 (게이트·전이·알림): 모든 rule 의 통계가 신선해진 뒤 두 축을 따로 판정한다.
     · **원장 축(사람)** — core.edge_policy.check_promotion(라우터 승격 게이트와 **동일 단일
       소스**)으로 candidate 자격 판정 → stats.promo_eligible 저장(프론트 '승격후보' 배지가 이
       값을 렌더링) → 알림: 승격 후보(게이트 전체 충족) / 집행 설계 필요(통계는 충족, 선정 시점
       실행 불가 피처). 판정일 1회이며 **어느 판정일인지는 정책이 정한다** — strict 는 확인창
       판정일, experimental 은 라우터 승격에서 판정 일정이 면제되므로 발견 판정일에 알린다
       (두 경로가 어긋나면 화면만 '검증 통과'가 된다). 승격·retire 는 관리자 API 수동 승인.
     · **운용 축(자동)** — live ↔ paused 를 core.edge_policy.decide_transition 으로 **이 워커가
       직접 전이시킨다**(승인 없음). 자는 시장 회귀 잔차 recent_alpha 이고 역할별 부호가 반대다
       (selector 는 매수 종목 alpha<0, veto 는 제외 종목 alpha>0 일 때 내린다). 절대 수익이
       아닌 이유는 그게 시장과 동기화돼 하락 구간엔 전 룰을 후보로 올리고 상승 구간엔 아무도
       못 걸렀기 때문이다. benchmark 는 제외(실탄이 아닌 페이퍼 기준선이라 유지 비용이 없다).
       **새 표본이 있는 실행에서만** 연속 카운트를 세고(stats.flip_streak), TRANSITION_STREAK
       표본일 연속일 때 전이한다. 알림은 승인 요청이 아니라 **사후 보고**이며 판정값
       alpha·beta·하락일 성적과 일 등가중 최근 평균을 병기해 "장이 나빠서인가 룰이 죽었나"를
       사람이 되짚을 수 있게 한다.
"""
import logging
import math
from datetime import date

from core.config import EDGE_COST_PCT, EDGE_PROMO_POLICY
from core.logging_setup import setup_logging
from core.edge_predicate import evaluate
from core.edge_policy import (
    CONFIRM_DAYS,
    DEMOTE_MIN_N,
    DISCOVERY_DAYS,
    check_confirmation,
    check_promotion,
    decide_transition,
    decision_due,
    decision_stage,
    rule_role,
)
from core.notifications import send_edge_rule_alert
from core.repository import (
    list_rules,
    get_stock_reports_by_date,
    get_report_dates_before_today,
    get_market_snapshots,
    get_scored_dates,
    upsert_rule_daily,
    get_rule_daily_since,
    get_universe_label_totals,
    set_rule_status,
    update_rule_decision,
    update_rule_stats,
)

setup_logging()
logger = logging.getLogger("RuleEvaluator")

_CI_Z = 1.64                     # 단측 95% 정규 근사
_RECENT_DAYS = 10                # 강등 감시: 최근 창의 **최소** 표본일 수 (stats.recent_* 산출 폭)
                                 # 실제 창은 적응형 — _recent_window 참고
_LABEL_RETRY_DEADLINE_DAYS = 14  # 결과 라벨 미도래 재시도 마감 — 초과 시 n=0 sentinel 로 종결
_FIT_MIN_DAYS = 5                # 시장 회귀(alpha·beta) 최소 거래일 — 미만이면 추정하지 않는다


def _recent_window(day_counts: list[tuple[str, int]]) -> set[str]:
    """강등 감시용 최근 창 = **max(표본일 _RECENT_DAYS 개, 종목-일 n 이 문턱을 채울 때까지)**.

    day_counts: [(날짜, 그날 매칭 종목 수)] 오래된→최신.

    창을 표본일 개수로만 고정하면 `n = 표본일 x 폭(1일당 매칭 종목 수)` 이 되어, **폭이 얇은
    룰은 표본이 아무리 쌓여도 DEMOTE_MIN_N 을 영원히 못 넘는다**(창이 고정이라 n 이 늘 수
    없다) — 그런 룰은 자동 전이 대상에서 영구히 빠진다. 창을 뒤로 늘려 문턱을 채우면 얇은 룰도
    '표본이 모이면 판정되는' 같은 규칙 아래 들어온다.
    두꺼운 룰은 _RECENT_DAYS 개에서 이미 문턱을 넘으므로 창이 늘지 않는다(동작 불변).
    창을 달력으로 제한하지는 않는다 — 드문 룰은 창이 길어 반응이 느린 게 그 룰의 성질이다.
    근거·실측: docs/history/edge-ledger.md
    """
    if not day_counts:
        return set()
    w = min(_RECENT_DAYS, len(day_counts))
    while w < len(day_counts) and sum(c for _, c in day_counts[-w:]) < DEMOTE_MIN_N:
        w += 1
    return {d for d, _ in day_counts[-w:]}


def _score_rule_date(rule: dict, rows: list[dict], market: dict | None) -> dict | None:
    """rule 을 한 날짜 유니버스에 적용. 결과 라벨 미도래면 None(스킵·재시도).

    반환: {n_matched, mean_net_ret, matched:[{code,name,ret,low}]} 또는 None.
    """
    label = rule["exit_label"]
    # 준비도: 그 날짜에 이 라벨이 하나라도 채워졌는가(아니면 백필 전 → 재시도).
    if not any(r.get(label) is not None for r in rows):
        return None

    matched, nets = [], []
    for r in rows:
        if not evaluate(rule["predicate"], r, market):
            continue
        ret = r.get(label)
        low = r.get("next_low_ret")
        matched.append({
            "code": r.get("stock_code"),
            "name": r.get("stock_name"),
            "ret": None if ret is None else round(float(ret), 3),
            "low": None if low is None else round(float(low), 3),
        })
        if ret is not None:
            nets.append(float(ret) - EDGE_COST_PCT)

    mean_net = round(sum(nets) / len(nets), 3) if nets else None
    return {"n_matched": len(matched), "mean_net_ret": mean_net, "matched": matched}


def _day_cluster_t(day_means: list[float]) -> tuple[float | None, float | None]:
    """일 등가중 평균과 그 t. 거래일 1일이면 분산 추정 불가라 t=None(게이트 fail-closed)."""
    if not day_means:
        return None, None
    mean_days = sum(day_means) / len(day_means)
    if len(day_means) < 2:
        return mean_days, None
    sd = (sum((x - mean_days) ** 2 for x in day_means) / (len(day_means) - 1)) ** 0.5
    if sd <= 0:
        return mean_days, None
    return mean_days, mean_days / (sd / math.sqrt(len(day_means)))


def _market_fit(pairs: list[tuple[float, float]]) -> tuple:
    """(그날 룰 수익, 그날 시장) 쌍을 회귀해 alpha·beta·t(alpha) 를 낸다.

        룰 일수익 = alpha + beta x 시장 + eps

    **초과수익(mean_exc)은 beta=1 을 강제한 특수케이스다.** 시장을 덜 따라가는(저beta) 룰은
    상승장에서 초과가 구조적으로 음수로 찍히지만, beta 를 추정해 빼면 "상승장엔 덜 벌어도
    하락장엔 버티는" 성질이 alpha 양수로 남는다. 강등 게이트가 이 alpha 를 쓴다.
    시장은 그날 **자기제외 유니버스 평균**(초과 계열과 같은 기준선)이라 룰 자신이 기준선에
    섞여 beta 가 부풀지 않는다. 비용은 룰 쪽에만 차감돼 alpha 가 흡수한다(순수익 기준 alpha).

    표본 부족(<_FIT_MIN_DAYS 거래일)이나 시장 분산 0 이면 (None, None, None) — fail-closed.
    근거·실측: docs/history/edge-ledger.md
    """
    n = len(pairs)
    if n < _FIT_MIN_DAYS:
        return None, None, None
    mx = sum(x for _, x in pairs) / n
    my = sum(y for y, _ in pairs) / n
    sxx = sum((x - mx) ** 2 for _, x in pairs)
    if sxx <= 0:
        return None, None, None
    beta = sum((y - my) * (x - mx) for y, x in pairs) / sxx
    alpha = my - beta * mx
    s2 = sum((y - (alpha + beta * x)) ** 2 for y, x in pairs) / (n - 2)
    se_a = math.sqrt(s2 * (1 / n + mx * mx / sxx)) if s2 > 0 else 0.0
    return alpha, beta, (alpha / se_a if se_a > 0 else None)


def _slice_sample_days(daily_rows: list[dict], start: int, end: int | None) -> list[dict]:
    """표본이 있는 거래일만 세어 [start, end) 구간의 daily_rows 를 잘라낸다.

    판정 일정(발견 1~10 / 확인 11~20)은 **달력일이 아니라 표본 거래일** 기준이다 — 매칭이
    드문 rule 은 달력으로 끊으면 표본 없이 판정일이 지나간다. n_matched=0 인 날(라벨 미도래
    sentinel 포함)은 세지 않으므로, 같은 구간이 언제 재계산해도 동일하게 재현된다.
    """
    out, idx = [], 0
    for dr in daily_rows:
        has = any(m.get("ret") is not None for m in (dr.get("matched") or []))
        if not has:
            continue
        if idx >= start and (end is None or idx < end):
            out.append(dr)
        idx += 1
    return out


def _recompute_stats(daily_rows: list[dict], uni_totals: dict | None = None) -> dict:
    """registered_at 이후 채점 결과에서 누적 통계 재계산(비용 차감 후 순수익 기준).

    세 계열을 함께 낸다 — 재는 자가 다르면 답도 다르기 때문에 이름으로 구분한다.
      · 원시(mean_net·ci_low·t_days)     : 절대 순수익. **승격·확인창·강등 게이트가 전부 이
        계열만 쓴다**(2026-08-04 사용자 결정 — "평균보다 크지 않아도 안정적으로 수익이 나면
        그만"). 이전에는 유의성만 초과 계열로 쟀고 대조군 우위 조건이 따로 있었다(둘 다 제거).
      · 초과(mean_exc·ci_low_exc·t_days_exc): 그날 **유니버스 자기제외 평균** 대비 초과분.
        **게이트에 쓰지 않는다 — 룰 상세 화면 표기·수동 검토 전용 진단값**이다. 계산을 남겨두는
        이유는 "장 덕에 올랐나"를 사람이 눈으로 확인할 수단은 여전히 필요하기 때문이다.
      · 시장 회귀(beta·alpha·t_alpha·recent_alpha·down_day_mean): 초과 계열이 beta=1 을 강제해
        **저beta 방어형 룰을 상승장에서 부당하게 죽이는** 문제를 푼다. **강등 게이트는
        recent_alpha 만** 쓰고 나머지는 표기용이다.

    왜 '자기제외'인가(2026-07-28): 대조군(=selected top10)을 기준선으로 쓰면 rule 매칭
    종목이 평균 54%(일부 100%) 그 안에 들어 있어 **자기 자신을 빼는** 꼴이 된다. 분산이
    기계적으로 줄어 잡음 감소처럼 보이지만 실제로는 초과분을 0 쪽으로 누르는 편향이다.
    유니버스에서 그 rule 의 매칭 종목을 제외한 나머지를 기준선으로 삼으면 편향이 0 이 되고,
    실측 잡음 감소는 26%(필요 거래일 1.8배 단축)다.
    비용(EDGE_COST_PCT)은 초과분에서 양쪽이 상쇄되므로 원시에만 적용한다.

    uni_totals: {report_date: (라벨 합계, 종목 수)} — 없으면 초과 계열은 None(표기만 '—' 가 된다).
    """
    nets, lows, dated, dated_exc, day_mkt = [], [], [], [], []
    updated_through = None
    for dr in daily_rows:
        updated_through = dr["report_date"]  # 오래된→최신 정렬이라 마지막이 최신
        d = dr["report_date"]
        matched = [m for m in (dr.get("matched") or []) if m.get("ret") is not None]
        for m in matched:
            net = m["ret"] - EDGE_COST_PCT
            nets.append(net)
            dated.append((d, net))
            if m.get("low") is not None:
                lows.append(m["low"])
        # 자기제외 기준선 — 유니버스 합계에서 이 rule 이 매칭한 종목의 원시 ret 을 뺀 평균.
        # 매칭이 유니버스 전체면(나머지 0종목) 비교 대상이 없으므로 그날은 초과 표본에서 뺀다.
        tot = (uni_totals or {}).get(d)
        if tot and matched:
            s, c = tot
            rest_n = c - len(matched)
            if rest_n > 0:
                base = (s - sum(m["ret"] for m in matched)) / rest_n
                for m in matched:
                    dated_exc.append((d, m["ret"] - base))
                # 시장 회귀용 (날짜, 그날 룰 일수익, 그날 시장) — alpha·beta 추정에 쓴다.
                day_mkt.append(
                    (d, sum(m["ret"] - EDGE_COST_PCT for m in matched) / len(matched), base))

    n = len(nets)
    if n == 0:
        return {"n": 0, "n_days": 0, "mean_net": None, "win_rate": None, "std": None,
                "ci_low": None, "mean_net_days": None, "t_days": None,
                "n_exc": 0, "mean_exc": None, "ci_low_exc": None,
                "mean_exc_days": None, "t_days_exc": None,
                "beta": None, "alpha": None, "t_alpha": None, "recent_alpha": None,
                "down_day_n": 0, "down_day_mean": None,
                "worst_low_ret": None, "updated_through": updated_through,
                "last_sample_date": None}

    mean_net = sum(nets) / n
    win_rate = sum(1 for x in nets if x > 0) / n
    std = (sum((x - mean_net) ** 2 for x in nets) / (n - 1)) ** 0.5 if n >= 2 else 0.0
    ci_low = mean_net - _CI_Z * std / math.sqrt(n)

    # 강등 감시용 최근 창(적응형 — _recent_window). 창을 종목-일 개수로 잡으면 광역
    # rule(일 10종목 매칭)에서 실효 3거래일밖에 안 돼 하루 시장 무브가 평균을 통째로 뒤집는다
    # (오탐 강등 사례: docs/history/edge-ledger.md).
    _day_counts: dict = {}
    for d, _ in dated:
        _day_counts[d] = _day_counts.get(d, 0) + 1
    recent_dates = _recent_window(sorted(_day_counts.items()))
    recent = [net for d, net in dated if d in recent_dates]
    recent_mean = sum(recent) / len(recent) if recent else None
    # 일 등가중 최근 평균 — 알림 병기용 진단값(게이트는 recent_alpha 를 쓴다). 시드가 하루
    # 총액 고정·종목 등분이라(seed_allocator: target=min(seed/n, cap)) 계좌 실현치는 종목-일
    # 가중이 아니라 이 값이다. 종목-일 가중과 부호가 갈리면 쏠림 신호.
    _recent_by_day: dict = {}
    for d, net in dated:
        if d in recent_dates:
            _recent_by_day.setdefault(d, []).append(net)
    recent_mean_days = (
        sum(sum(v) / len(v) for v in _recent_by_day.values()) / len(_recent_by_day)
        if _recent_by_day else None
    )

    # ── 일 클러스터 통계 — 위 ci_low 는 종목-일 iid 가정이라 같은 날 종목들이 시장 무브로
    # 상관된 만큼 유의성을 과신한다. 거래일을 관측 단위로 묶어(하루 1표본) 다시 재면 실효
    # 유의성이 나온다(이 차이로 뒤집힌 후보 사례: docs/history/edge-ledger.md).
    # mean_net_days(일 등가중 평균)는 mean_net(종목-일 가중)과 다르다 — 매칭 수가 많은 날에
    # 쏠린 평균을 드러낸다.
    def _by_day(pairs):
        acc = {}
        for d, v in pairs:
            acc.setdefault(d, []).append(v)
        return [sum(v) / len(v) for v in acc.values()]

    mean_days, t_days = _day_cluster_t(_by_day(dated))

    # 초과 계열 — **표기·수동 검토용 진단값**(게이트에서는 쓰지 않는다). 표본 없으면 None.
    n_exc = len(dated_exc)
    if n_exc:
        exc = [v for _, v in dated_exc]
        mean_exc = sum(exc) / n_exc
        std_exc = (sum((x - mean_exc) ** 2 for x in exc) / (n_exc - 1)) ** 0.5 if n_exc >= 2 else 0.0
        ci_low_exc = mean_exc - _CI_Z * std_exc / math.sqrt(n_exc)
        mean_exc_days, t_days_exc = _day_cluster_t(_by_day(dated_exc))
    else:
        mean_exc = ci_low_exc = mean_exc_days = t_days_exc = None

    # ── 시장 회귀 계열 (alpha·beta) — **강등 게이트가 recent_alpha 를 쓴다** ──
    # 절대 recent_mean_net 은 시장과 동기화돼 하락 구간엔 멀쩡한 룰까지 한꺼번에 강등 후보로
    # 올리고 상승 구간엔 아무도 못 걸렀다. 초과수익(beta=1 강제)은 반대로 저beta 방어형 룰을
    # 상승장에서 부당하게 죽인다. beta 를 추정해 빼는 alpha 가 양쪽을 다 피한다.
    alpha, beta, t_alpha = _market_fit([(y, x) for _, y, x in day_mkt])
    # **beta 는 전체 표본, alpha 만 최근 창.** 최근 10거래일로 beta 까지 추정하면 se(beta)≈0.3
    # 이라 판정이 불가능하다. beta 는 룰의 구조적 성질(롱온리 종가베팅이라 대개 0.5~1.5)이라
    # 천천히 변하고, "엣지가 사라졌다"는 alpha 가 음수로 도는 것으로 나타난다.
    recent_pairs = [(y, x) for d, y, x in day_mkt if d in recent_dates]
    recent_alpha = None
    if beta is not None and recent_pairs:
        k = len(recent_pairs)
        recent_alpha = (sum(y for y, _ in recent_pairs) / k
                        - beta * (sum(x for _, x in recent_pairs) / k))
    # 하락일 성적 — "상승장엔 덜 벌어도 하락장엔 안 잃는가"를 직접 재는 값(표기 전용).
    # alpha 와 달리 모형 가정이 없어 사람이 눈으로 확인하기 쉽다.
    down = [y for _, y, x in day_mkt if x < 0]

    return {
        "n": n,
        # 라벨 표본이 있는 서로 다른 거래일 수 — 같은 날 표본은 시장 무브로 상관되어
        # 실효 표본은 n 이 아니라 이 값에 가깝다(승격 게이트 PROMO_MIN_DAYS 가 사용).
        "n_days": len({d for d, _ in dated}),
        "mean_net": round(mean_net, 3),
        "win_rate": round(win_rate, 3),
        "std": round(std, 3),
        "ci_low": round(ci_low, 3),
        # 원시 일 등가중 평균과 그 t — **게이트(유의성)가 쓰는 값**이자 쏠림 진단값.
        "mean_net_days": round(mean_days, 3) if mean_days is not None else None,
        "t_days": round(t_days, 2) if t_days is not None else None,
        # ── 유니버스 자기제외 초과 계열 — 룰 상세 화면 표기 전용(게이트 미사용) ──
        "n_exc": n_exc,
        "mean_exc": round(mean_exc, 3) if mean_exc is not None else None,
        "ci_low_exc": round(ci_low_exc, 3) if ci_low_exc is not None else None,
        "mean_exc_days": round(mean_exc_days, 3) if mean_exc_days is not None else None,
        "t_days_exc": round(t_days_exc, 2) if t_days_exc is not None else None,
        # ── 시장 회귀 계열 — beta·alpha·t_alpha 는 누적 표본, recent_alpha 는 최근 창 ──
        # recent_alpha 만 게이트(check_demotion)가 쓰고 나머지는 화면·수동 검토용 진단값이다.
        "beta": round(beta, 3) if beta is not None else None,
        "alpha": round(alpha, 3) if alpha is not None else None,
        "t_alpha": round(t_alpha, 2) if t_alpha is not None else None,
        "recent_alpha": round(recent_alpha, 3) if recent_alpha is not None else None,
        # 시장이 내린 날(자기제외 유니버스 평균<0)만 모은 성적 — 표기 전용.
        "down_day_n": len(down),
        "down_day_mean": round(sum(down) / len(down), 3) if down else None,
        "worst_low_ret": round(min(lows), 3) if lows else None,
        "updated_through": updated_through,
        # 마지막으로 **표본이 생긴** 날. updated_through 는 매칭 0 인 날에도 갱신되므로
        # 자동 전이의 '새 정보가 있었나' 판정에는 쓸 수 없다 — 그걸로 세면 연속 카운트가
        # 표본일이 아니라 달력 평일이 되어, 안 바뀐 alpha 가 반복 집계된다.
        "last_sample_date": max(d for d, _ in dated),
        "recent_n": len(recent),
        "recent_n_days": len(recent_dates),
        "recent_mean_net": round(recent_mean, 3) if recent_mean is not None else None,
        # 강등 게이트가 쓰는 값 — 계좌 실현치와 같은 가중(일 등가중)
        "recent_mean_net_days": round(recent_mean_days, 3) if recent_mean_days is not None else None,
    }


def _refresh_missing_lows(rule_id: int, daily_rows: list[dict], universe) -> int:
    """채점 당시 미도래였던 next_low_ret 를 matched 스냅샷에 소급 반영. 반환: 갱신 날짜 수.

    exec_leg_ret(분봉)는 D+1 아침에 채워져 그날 채점되지만, next_low_ret(일봉)는 D+1 캔들이
    완결된 D+2 에야 백필된다. 스냅샷의 low=None 을 그대로 두면 worst_low_ret(꼬리 리스크
    지표)가 모든 rule 에서 영원히 비므로, 재시도 마감 전 날짜에 한해 현재 값으로 채운다.
    daily_rows 의 matched 를 in-place 갱신하므로 직후 _recompute_stats 에 바로 반영된다.
    """
    refreshed = 0
    for dr in daily_rows:
        d = str(dr["report_date"])
        matched = dr.get("matched") or []
        holes = [m for m in matched if m.get("low") is None]
        if not holes or _past_deadline(d):
            continue
        low_map = {
            r["stock_code"]: r["next_low_ret"]
            for r in universe(d)
            if r.get("next_low_ret") is not None
        }
        changed = False
        for m in holes:
            low = low_map.get(m.get("code"))
            if low is not None:
                m["low"] = round(float(low), 3)
                changed = True
        if changed:
            upsert_rule_daily(rule_id, d, dr["n_matched"], dr.get("mean_net_ret"), matched)
            refreshed += 1
    return refreshed


def _past_deadline(d: str) -> bool:
    """채점 후보 날짜 d 가 재시도 마감을 넘겼는가 — 실시간 라벨(nxt_open_ret 등)은 소급
    수집이 불가해, 그날 수집이 최종 실패했다면 영원히 준비되지 않는다. 마감 초과 시
    n=0 sentinel 로 종결해 매일 같은 날짜의 유니버스를 재조회하는 낭비를 끊는다."""
    try:
        return (date.today() - date.fromisoformat(d)).days > _LABEL_RETRY_DEADLINE_DAYS
    except ValueError:
        return False


def run():
    # retired 도 채점한다(2026-07-31 사용자 결정) — retire 는 '판정 종결'이고 관측은 계속이다.
    # pass 2 의 게이트 분기가 candidate/live 만 타므로 알림·승격·강등에는 올라오지 않는다.
    rules = list_rules()
    if not rules:
        logger.info("활성 rule 없음 — 종료")
        return

    all_dates = get_report_dates_before_today()
    if not all_dates:
        logger.info("채점 후보 날짜 없음 — 종료")
        return

    # 유니버스·시장 스냅샷은 날짜별 1회 로드 후 rule 간 공유(캐시)
    uni_cache: dict[str, list[dict]] = {}
    mkt_cache: dict[str, dict | None] = {}

    def _universe(d: str) -> list[dict]:
        if d not in uni_cache:
            uni_cache[d] = get_stock_reports_by_date(d, include_unselected=True)
        return uni_cache[d]

    def _market(d: str) -> dict | None:
        if d not in mkt_cache:
            mkt_cache[d] = get_market_snapshots([d]).get(d)
        return mkt_cache[d]

    # 초과수익 기준선 — exit_label 별 날짜별 (유니버스 합계, 종목 수)를 1회 로드해 rule 간
    # 공유한다. rule 마다 빼야 할 매칭 종목이 달라 평균이 아니라 합계·개수로 들고 있어야
    # _recompute_stats 가 '자기제외' 평균을 만들 수 있다.
    uni_totals_by_label: dict[str, dict] = {}
    for label in {r.get("exit_label") or "exec_leg_ret" for r in rules}:
        try:
            uni_totals_by_label[label] = get_universe_label_totals(label)
        except ValueError as e:
            logger.warning(
                f"초과수익 기준선 로드 실패({label}): {e} — 해당 rule 은 원시 계열만 채점되고, "
                "recent_alpha 가 비어 **강등 감시가 멈춘다**(fail-closed)")
            uni_totals_by_label[label] = {}

    logger.info(f"평가 시작 — 활성 rule {len(rules)}개 × 후보 {len(all_dates)}일 (비용 {EDGE_COST_PCT}%)")

    # ── pass 1: 채점 + 누적 통계 재계산 (rule dict 에 신선한 stats 를 실어 pass 2 로) ──
    for rule in rules:
        scored = get_scored_dates(rule["id"])
        pending = [d for d in all_dates if d >= str(rule["registered_at"]) and d not in scored]
        new_scored = expired = 0
        for d in pending:
            result = _score_rule_date(rule, _universe(d), _market(d))
            if result is None:
                if _past_deadline(d):
                    # 라벨 영구 미도래 — sentinel(n=0, matched=[])로 종결. 통계엔 무영향.
                    upsert_rule_daily(rule["id"], d, 0, None, [])
                    expired += 1
                continue  # 라벨 미도래 — 다음 실행에서 재시도
            upsert_rule_daily(
                rule["id"], d, result["n_matched"], result["mean_net_ret"], result["matched"]
            )
            new_scored += 1
        if expired:
            logger.warning(
                f"{rule['name']}: 라벨({rule['exit_label']}) 미도래 {expired}일을 "
                f"{_LABEL_RETRY_DEADLINE_DAYS}일 마감 초과로 sentinel 종결"
            )

        # 누적 통계 재계산(사전 등록일 이후 표본만) — 그 전에 미도래였던 low 스냅샷을 소급 갱신
        daily_rows = get_rule_daily_since(rule["id"], str(rule["registered_at"]))
        low_refreshed = _refresh_missing_lows(rule["id"], daily_rows, _universe)
        if low_refreshed:
            logger.info(f"{rule['name']}: next_low_ret 소급 반영 {low_refreshed}일")
        rule["_uni"] = uni_totals_by_label.get(rule.get("exit_label") or "exec_leg_ret")
        # 자동 전이 연속 카운트는 stats 재계산에 살아남아야 한다(직전 실행에서 이어받는 값).
        # 함께 들고 오는 직전 **last_sample_date** 로 "이번 실행에 새 표본이 있었나"를 판정한다
        # (updated_through 가 아니다 — 그건 매칭 0 인 날에도 움직인다).
        _prev = rule.get("stats") or {}
        rule["_prev_flip_streak"] = _prev.get("flip_streak") or 0
        rule["_prev_sample_date"] = _prev.get("last_sample_date")
        rule["stats"] = _recompute_stats(daily_rows, rule["_uni"])
        rule["_daily_rows"] = daily_rows   # pass2 판정이 발견/확인 구간으로 잘라 쓴다
        rule["_new_scored"] = new_scored

    # ── pass 2: 승격/강등 게이트 (모든 rule 의 stats 가 신선해진 뒤 — 판정 시점 정합) ──
    controls = [r for r in rules if rule_role(r) == "benchmark" and r["status"] == "live"]
    promotions, exec_pending, transitions = [], [], []
    for rule in rules:
        stats = rule["stats"]
        # 적용 중인 심사 정책은 **전역 설정**이라 상태와 무관하게 전 rule 에 남긴다 — candidate
        # 에만 붙이면 후보가 0 종인 순간 화면에서 정책 표시가 사라진다.
        stats["promo_policy"] = EDGE_PROMO_POLICY
        if rule["status"] == "candidate":
            gate = check_promotion(rule, controls, policy=EDGE_PROMO_POLICY)  # 라우터와 동일 단일 소스
            stats["promo_eligible"] = gate["eligible"]
            stats["decision_stage"] = decision_stage(rule)
            # 화면이 게이트를 **재추정하지 않도록** 막고 있는 항목과 적용 정책을 함께 저장한다.
            # (프론트가 조건을 따로 계산하면 게이트가 바뀔 때마다 '게이지는 꽉 찼는데 검증 중'
            #  같은 불일치가 난다 — 조건은 백엔드만 안다. 사례: docs/history/frontend-ui.md)
            # 사유 문자열의 콜론 앞부분만 잘라 짧은 라벨로 만든다(문구가 바뀌어도 자동 동기화).
            stats["promo_blockers"] = [
                r.split(":")[0].strip() for r in (gate["stat_reasons"] + gate["exec_reasons"])
            ]
            stats["promo_policy"] = EDGE_PROMO_POLICY
            row = {
                "name": rule["name"], "family": rule["family"], "role": rule_role(rule),
                "n": stats["n"], "mean_net": stats["mean_net"], "ci_low": stats["ci_low"],
            }
            # ── 판정 일정 — 게이트를 '매일' 검사하면 무기한 재시험이 되어 오탐률이 몇 배로 뛴다.
            # 판정은 사전에 정한 시점에 1회만 하고 기록한다.
            # benchmark 는 실탄이 아니라 기준선이므로 일정 밖(알림 대상도 아님).
            due = decision_due(rule, stats.get("n_days") or 0) if rule_role(rule) != "benchmark" else None
            if due == "discovery":
                d_stats = _recompute_stats(
                    _slice_sample_days(rule["_daily_rows"], 0, DISCOVERY_DAYS), rule["_uni"])
                d_gate = check_promotion({**rule, "stats": d_stats}, controls, policy=EDGE_PROMO_POLICY)
                # 발견 판정은 **통계만** 본다. 선정 시점 실행 불가(exec_reasons)는 가설이
                # 반증된 게 아니라 집행 설계 문제이고, 설계가 바뀌면 되살아나야 한다
                # (veto_short_surge 사례: short_wght 가 17:50 수집이라 실행 불가지만 통계는
                # 별개). exec 사유로 종결시키면 설계 변경 후 재검토 경로가 사라진다.
                d_pass = not d_gate["stat_reasons"]
                rule["decision"] = {
                    "discovery": {
                        "at": str(date.today()), "n_days": d_stats.get("n_days"),
                        "pass": d_pass,
                        # 판정에 쓴 값(mean_net·t_days)을 기록하고, 초과 계열은 참고로 병기한다.
                        "mean_net": d_stats.get("mean_net"), "t_days": d_stats.get("t_days"),
                        "mean_exc": d_stats.get("mean_exc"), "t_days_exc": d_stats.get("t_days_exc"),
                        "reasons": d_gate["stat_reasons"],
                        "exec_blocked": d_gate["exec_reasons"] or None,
                    },
                }
                if not d_pass:
                    # 발견 탈락 = 종결. 자동 retire 는 하지 않는다(전이는 관리자 수동).
                    rule["decision"]["decided_at"] = str(date.today())
                    rule["decision"]["verdict"] = "discovery_failed"
                update_rule_decision(rule["id"], rule["decision"])
                logger.info(
                    f"[판정:발견] {rule['name']} — {'통과→확인창 대기' if d_pass else '탈락(종결)'}"
                    f"{' (단 선정 시점 실행 불가)' if d_gate['exec_reasons'] else ''}"
                    f" (거래일 {d_stats.get('n_days')}, 평균수익 {d_stats.get('mean_net')}%, "
                    f"t {d_stats.get('t_days')}, 참고 초과 {d_stats.get('mean_exc')}%)"
                )
                # experimental 은 라우터 승격에서 **판정 일정이 면제**되므로(routers/edge_rule.py)
                # 발견 통과 시점에 이미 승격 가능하다. 확인창까지 기다려 알리면 화면은 '검증 통과'
                # 인데 알림만 없는 구간이 최대 CONFIRM_DAYS 거래일 생긴다 → 두 경로를 맞춘다.
                # strict 에서는 그대로 확인창 판정까지 알리지 않는다.
                if d_pass and EDGE_PROMO_POLICY == "experimental":
                    if d_gate["exec_reasons"]:
                        exec_pending.append(
                            {**row, "reason": d_gate["exec_reasons"][0], "stage": "discovery"})
                    else:
                        promotions.append(
                            {**row, "mean_exc": d_stats.get("mean_exc"), "stage": "discovery"})
            elif due == "confirm":
                c_stats = _recompute_stats(
                    _slice_sample_days(rule["_daily_rows"], DISCOVERY_DAYS,
                                       DISCOVERY_DAYS + CONFIRM_DAYS), rule["_uni"])
                # 확인창은 **role 별로 부호가 반대다**(2026-07-29) — 자는 양쪽 다 mean_net 이고
                # veto 만 <0 을 본다. role 을 안 넘기면 veto 가 '잘 작동한다는 이유로' 종결된다.
                conf = check_confirmation(c_stats, rule_role(rule))
                dec = dict(rule.get("decision") or {})
                dec["confirm"] = {
                    "at": str(date.today()), "n_days": conf["n_days"],
                    "pass": conf["pass"], "mean_exc": conf["mean_exc"],
                    "mean_net": conf.get("mean_net"), "reasons": conf["reasons"],
                }
                dec["decided_at"] = str(date.today())
                dec["verdict"] = "confirmed" if conf["pass"] else "confirm_failed"
                rule["decision"] = dec
                update_rule_decision(rule["id"], dec)
                logger.info(
                    f"[판정:확인] {rule['name']} — {'확증(승격 후보)' if conf['pass'] else '재현 실패(종결)'}"
                    f" (확인창 거래일 {conf['n_days']}, 평균수익 {conf.get('mean_net')}%, "
                    f"참고 초과 {conf['mean_exc']}%)"
                )
                if conf["pass"]:
                    # 확인창까지 통과 — 이때만 알린다. 실행 가능성은 여기서 다시 확인한다
                    # (통계는 확증됐는데 선정 시점 실행 불가면 '집행 설계 필요' 분기).
                    if gate["exec_reasons"]:
                        exec_pending.append(
                            {**row, "reason": gate["exec_reasons"][0], "stage": "confirm"})
                    else:
                        promotions.append({
                            **row,
                            "confirm_mean_net": c_stats.get("mean_net"),   # 판정에 쓴 값
                            "mean_exc": c_stats.get("mean_exc"),           # 참고 표기
                            "stage": "confirm",
                        })
        elif rule["status"] in ("live", "paused"):
            # ── 운용 전이(live ↔ paused) — 자동. 판정은 core.edge_policy.decide_transition ──
            # 새 표본이 없는 실행에서는 alpha 가 그대로라 **아무 것도 세지 않는다**(같은 값을
            # 두 번 세면 새 정보 없이 상태가 바뀐다). 연속 단위가 표본일인 이유가 이것이다.
            fresh = (stats["last_sample_date"] is not None
                     and stats["last_sample_date"] != rule.get("_prev_sample_date"))
            streak = rule.get("_prev_flip_streak") or 0
            if fresh:
                t = decide_transition(rule, streak)
                streak = t["streak"]
                if t["next_status"]:
                    set_rule_status(rule["id"], t["next_status"])
                    streak = 0
                    transitions.append({
                        "name": rule["name"], "family": rule["family"], "role": rule_role(rule),
                        "from": rule["status"], "to": t["next_status"], "reason": t["reason"],
                        # 판정값(시장 조정 alpha)과 그 재료(beta·하락일 성적)를 함께 —
                        # alpha 만 보면 "장이 나빠서인가"를 사람이 되짚을 수 없다.
                        "alpha": stats["recent_alpha"], "beta": stats["beta"],
                        "down_day_mean": stats["down_day_mean"],
                        "down_day_n": stats["down_day_n"],
                        # 절대 수익(종목-일 가중)은 판정 자가 아니라 참고값이다.
                        "n": stats["recent_n"], "mean_net": stats["recent_mean_net"],
                        # 일 등가중 최근 평균을 병기 — 두 가중의 부호가 갈리면 쏠림(몇 종목의
                        # 급등이 만든 평균)이라 판단 재료가 약하다(notifications 가 ⚠️ 표시).
                        "mean_net_days": stats["recent_mean_net_days"],
                    })
                    rule["status"] = t["next_status"]
            stats["flip_streak"] = streak

        update_rule_stats(rule["id"], stats)
        logger.info(
            f"[건강지표] {rule['name']} ({rule['family']}/{rule['status']}) — "
            f"신규 {rule.get('_new_scored', 0)}일, n={stats['n']}, 평균순수익={stats['mean_net']}, "
            f"승률={stats['win_rate']}, CI하한={stats['ci_low']}, alpha={stats['alpha']}, "
            f"beta={stats['beta']}, 최근alpha={stats['recent_alpha']}, "
            f"최악저가={stats['worst_low_ret']}"
        )

    if promotions or transitions or exec_pending:
        send_edge_rule_alert(promotions, transitions, exec_pending)
    logger.info(
        f"평가 완료 — 승격 후보 {len(promotions)} / 집행 설계 필요 {len(exec_pending)} / "
        f"운용 전이 {len(transitions)}"
    )


if __name__ == "__main__":
    run()
