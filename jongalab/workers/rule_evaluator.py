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
  pass 2 (게이트·알림): 모든 rule 의 통계가 신선해진 뒤 core.edge_policy.check_promotion
     (라우터 승격 게이트와 **동일 단일 소스**)으로 자격 판정 → stats.promo_eligible 저장
     (프론트 '승격후보' 배지가 이 값을 렌더링) → 텔레그램 알림:
       승격 후보(게이트 전체 충족) / 집행 설계 필요(통계는 충족, 선정 시점 실행 불가 피처) /
       강등 검토(core.edge_policy.check_demotion — live 비대조군, 최근 10거래일 창
       n≥20·거래일≥5 + **역할별 부호**: selector 는 매수 종목 mean_net<0, veto 는 제외 종목
       mean_net>0(이기는 종목을 버리는 중)일 때. benchmark 는 제외 — live 대조군이 사라지면
       승격 게이트가 fail-closed 로 전 후보를 막는다).
     실제 전이는 관리자 API 수동 승인.
"""
import logging
import math
from datetime import date

from core.config import EDGE_COST_PCT
from core.logging_setup import setup_logging
from core.edge_predicate import evaluate
from core.edge_policy import check_demotion, check_promotion, rule_role
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
    update_rule_stats,
)

setup_logging()
logger = logging.getLogger("RuleEvaluator")

_CI_Z = 1.64                     # 단측 95% 정규 근사
_RECENT_DAYS = 10                # 강등 감시: 최근 창(거래일 수) — stats.recent_* 산출 폭
                                 # 강등 판정 문턱(표본·거래일·부호)은 core.edge_policy.check_demotion
_LABEL_RETRY_DEADLINE_DAYS = 14  # 결과 라벨 미도래 재시도 마감 — 초과 시 n=0 sentinel 로 종결


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


def _recompute_stats(daily_rows: list[dict], uni_totals: dict | None = None) -> dict:
    """registered_at 이후 채점 결과에서 누적 통계 재계산(비용 차감 후 순수익 기준).

    두 계열을 함께 낸다 — 재는 자가 다르면 답도 다르기 때문에 이름으로 구분한다.
      · 원시(mean_net·ci_low·t_days)     : 절대 순수익. **대조군 우위** 게이트와 veto
        실익 게이트가 쓴다("현행 선정보다 나은가"는 절대값으로 물어야 답이 된다).
      · 초과(mean_exc·ci_low_exc·t_days_exc): 그날 **유니버스 자기제외 평균** 대비 초과분.
        selector 승격의 통계 유의성(ci_low_exc>0, t_days_exc≥PROMO_MIN_DAY_T)이 쓴다.

    왜 '자기제외'인가(2026-07-28): 대조군(=selected top10)을 기준선으로 쓰면 rule 매칭
    종목이 평균 54%(일부 100%) 그 안에 들어 있어 **자기 자신을 빼는** 꼴이 된다. 분산이
    기계적으로 줄어 잡음 감소처럼 보이지만 실제로는 초과분을 0 쪽으로 누르는 편향이다.
    유니버스에서 그 rule 의 매칭 종목을 제외한 나머지를 기준선으로 삼으면 편향이 0 이 되고,
    실측 잡음 감소는 26%(필요 거래일 1.8배 단축)다.
    비용(EDGE_COST_PCT)은 초과분에서 양쪽이 상쇄되므로 원시에만 적용한다.

    uni_totals: {report_date: (라벨 합계, 종목 수)} — 없으면 초과 계열은 None(게이트 fail-closed).
    """
    nets, lows, dated, dated_exc = [], [], [], []
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

    n = len(nets)
    if n == 0:
        return {"n": 0, "n_days": 0, "mean_net": None, "win_rate": None, "std": None,
                "ci_low": None, "mean_net_days": None, "t_days": None,
                "n_exc": 0, "mean_exc": None, "ci_low_exc": None,
                "mean_exc_days": None, "t_days_exc": None,
                "worst_low_ret": None, "updated_through": updated_through}

    mean_net = sum(nets) / n
    win_rate = sum(1 for x in nets if x > 0) / n
    std = (sum((x - mean_net) ** 2 for x in nets) / (n - 1)) ** 0.5 if n >= 2 else 0.0
    ci_low = mean_net - _CI_Z * std / math.sqrt(n)

    # 강등 감시용 최근 창 — 최근 _RECENT_DAYS 거래일의 표본. 종목-일 30개 창은 광역 rule
    # (일 10종목 매칭)에서 거래일 3일에 불과해, 하루 시장 무브가 평균을 통째로 뒤집는
    # 오탐 강등 알림을 냈다(2026-07-20 control_legacy_top10 사례).
    recent_dates = set(sorted({d for d, _ in dated})[-_RECENT_DAYS:])
    recent = [net for d, net in dated if d in recent_dates]
    recent_mean = sum(recent) / len(recent) if recent else None

    # ── 일 클러스터 통계 (2026-07-28) — 위 ci_low 는 종목-일 iid 가정이라 같은 날 종목들이
    # 시장 무브로 상관된 만큼 유의성을 과신한다. 거래일을 관측 단위로 묶어(하루 1표본) 다시 재면
    # 실효 유의성이 나온다. 두 selector 후보가 이 차이로 뒤집혔다:
    #   f5_prog_persistent(7/27) iid t=1.82 → 일 t=0.47 / f4_sector_follower(7/28) 1.99 → 0.37.
    # mean_net_days(일 등가중 평균)는 mean_net(종목-일 가중)과 다르다 — 매칭 수가 많은 날에
    # 쏠린 평균을 드러낸다(f4: mean_net +1.19% vs 일 등가중 +0.45%).
    def _by_day(pairs):
        acc = {}
        for d, v in pairs:
            acc.setdefault(d, []).append(v)
        return [sum(v) / len(v) for v in acc.values()]

    mean_days, t_days = _day_cluster_t(_by_day(dated))

    # 초과 계열 — selector 승격 게이트가 보는 값. 표본이 없으면 전부 None → fail-closed.
    n_exc = len(dated_exc)
    if n_exc:
        exc = [v for _, v in dated_exc]
        mean_exc = sum(exc) / n_exc
        std_exc = (sum((x - mean_exc) ** 2 for x in exc) / (n_exc - 1)) ** 0.5 if n_exc >= 2 else 0.0
        ci_low_exc = mean_exc - _CI_Z * std_exc / math.sqrt(n_exc)
        mean_exc_days, t_days_exc = _day_cluster_t(_by_day(dated_exc))
    else:
        mean_exc = ci_low_exc = mean_exc_days = t_days_exc = None

    return {
        "n": n,
        # 라벨 표본이 있는 서로 다른 거래일 수 — 같은 날 표본은 시장 무브로 상관되어
        # 실효 표본은 n 이 아니라 이 값에 가깝다(승격 게이트 PROMO_MIN_DAYS 가 사용).
        "n_days": len({d for d, _ in dated}),
        "mean_net": round(mean_net, 3),
        "win_rate": round(win_rate, 3),
        "std": round(std, 3),
        "ci_low": round(ci_low, 3),
        # 원시 일 등가중 평균과 그 t — 참고·표시용(쏠림 진단). 게이트는 아래 초과 계열을 본다.
        "mean_net_days": round(mean_days, 3) if mean_days is not None else None,
        "t_days": round(t_days, 2) if t_days is not None else None,
        # ── 유니버스 자기제외 초과 계열 — selector 승격 통계 게이트가 쓰는 값 ──
        "n_exc": n_exc,
        "mean_exc": round(mean_exc, 3) if mean_exc is not None else None,
        "ci_low_exc": round(ci_low_exc, 3) if ci_low_exc is not None else None,
        "mean_exc_days": round(mean_exc_days, 3) if mean_exc_days is not None else None,
        "t_days_exc": round(t_days_exc, 2) if t_days_exc is not None else None,
        "worst_low_ret": round(min(lows), 3) if lows else None,
        "updated_through": updated_through,
        "recent_n": len(recent),
        "recent_n_days": len(recent_dates),
        "recent_mean_net": round(recent_mean, 3) if recent_mean is not None else None,
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
    rules = list_rules(exclude_retired=True)
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
            logger.warning(f"초과수익 기준선 로드 실패({label}): {e} — 해당 rule 은 원시 계열만 채점")
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
        rule["stats"] = _recompute_stats(
            daily_rows, uni_totals_by_label.get(rule.get("exit_label") or "exec_leg_ret")
        )
        rule["_new_scored"] = new_scored

    # ── pass 2: 승격/강등 게이트 (모든 rule 의 stats 가 신선해진 뒤 — 대조군 비교 정합) ──
    controls = [r for r in rules if rule_role(r) == "benchmark" and r["status"] == "live"]
    promotions, exec_pending, demotions = [], [], []
    for rule in rules:
        stats = rule["stats"]
        if rule["status"] == "candidate":
            gate = check_promotion(rule, controls)  # 라우터 승격 게이트와 동일 단일 소스
            stats["promo_eligible"] = gate["eligible"]
            row = {
                "name": rule["name"], "family": rule["family"],
                "n": stats["n"], "mean_net": stats["mean_net"], "ci_low": stats["ci_low"],
            }
            # benchmark(측정용) 후보는 게이트 전면 면제라 항상 eligible 이지만, '실전 투입'
            # 알림 대상이 아니다(기준선 교체는 필요 시 관리자가 API 로 의도적으로 수행).
            if gate["eligible"] and rule_role(rule) != "benchmark":
                promotions.append(row)
            elif (
                not gate["stat_reasons"] and gate["exec_reasons"]
                and stats["n"] >= (rule.get("min_sample") or 0)
            ):
                # 통계 게이트 통과 + 표본 충족인데 선정 시점 실행 불가 피처만 남은 페이퍼 엣지 —
                # 집행 설계(선정 시점 이동 등) 검토 대상. 표본 미달엔 알리지 않는다(매일 스팸 방지).
                exec_pending.append({**row, "reason": gate["exec_reasons"][0]})
        elif rule["status"] == "live":
            # 강등 게이트도 core.edge_policy 단일 소스 — 역할별 mean_net 부호가 반대다
            # (selector 는 음수, veto 는 제외 종목이 양수일 때 강등 검토). benchmark 면제.
            if check_demotion(rule)["demote_candidate"]:
                demotions.append({
                    "name": rule["name"], "family": rule["family"],
                    "n": stats["recent_n"], "mean_net": stats["recent_mean_net"],
                })

        update_rule_stats(rule["id"], stats)
        logger.info(
            f"[건강지표] {rule['name']} ({rule['family']}/{rule['status']}) — "
            f"신규 {rule.get('_new_scored', 0)}일, n={stats['n']}, 평균순수익={stats['mean_net']}, "
            f"승률={stats['win_rate']}, CI하한={stats['ci_low']}, 최악저가={stats['worst_low_ret']}"
        )

    if promotions or demotions or exec_pending:
        send_edge_rule_alert(promotions, demotions, exec_pending)
    logger.info(
        f"평가 완료 — 승격 후보 {len(promotions)} / 집행 설계 필요 {len(exec_pending)} / 강등 검토 {len(demotions)}"
    )


if __name__ == "__main__":
    run()
