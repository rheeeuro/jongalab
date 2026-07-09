"""선정 레이어 — 모드별 selected 판정 (순수 로직, DB·네트워크 무의존).

closing_bet 이 점수·rank_no·저장을 마친 뒤, 어떤 종목을 실매매로 핸드오프할지(selected)만
이 함수로 정한다. trading_engine(가드 파일)·점수 계산은 건드리지 않는다.

모드(EDGE_SELECTION_MODE):
  legacy : 점수 rank_no ≤ top_n (현행) — rule_names 없음(NULL)
  hybrid : live rule 매칭 종목 우선 + 잔여 슬롯 점수순, 총 상한 top_n
  rules  : live rule 매칭 합집합만(상한 초과 시 rule 기대값 mean_net 순). 매칭 0 = 무거래

veto(감액·제외) rule 은 모드 무관하게 선정 직전 적용(reduce-only — 제외만, 승급 없음).

⚠️ 선정 시점(closing_bet 13~15시)엔 NXT 스냅샷(nxt_gap_pct 등)·당일 market_snapshot 이
아직 없다(19:50 수집). 그 컬럼을 참조하는 rule 은 predicate 상 NULL→매칭실패라 이 시점 선정에
기여하지 못한다(F1 뉴스·F4 섹터처럼 13~15시에 채워지는 피처 기반 rule 만 유효). 의도된 보수 동작.

DB 무의존 순수 함수 → tests/test_edge_selection.py 가 계약을 고정한다.
"""
from core.edge_predicate import evaluate

MODES = ("legacy", "hybrid", "rules")


def _code(c: dict):
    return c.get("stock_code") or c.get("stk_cd")


def _rank(c: dict) -> int:
    r = c.get("rank_no")
    return r if r is not None else 10**9


def _mean_net(rule: dict):
    return (rule.get("stats") or {}).get("mean_net")


def _matches(rule: dict, row: dict, market: dict | None) -> bool:
    """predicate 평가 — 잘못된 rule 은 선정에 영향 주지 않도록 False(등록 시점에 검증됨)."""
    try:
        return evaluate(rule.get("predicate") or [], row, market)
    except Exception:
        return False


def select_signals(
    mode: str,
    candidates: list[dict],
    live_rules: list[dict],
    veto_rules: list[dict],
    top_n: int,
    market: dict | None = None,
) -> tuple[list[str], dict[str, str], list[dict]]:
    """모드별 selected 판정.

    candidates: 점수순(rank_no 오름차순) 정렬된 리포트 행 dict 목록.
    live_rules: role=selector 인 live rule dict 목록(name·predicate·stats). veto_rules: role=veto live rule.
    반환: (selected_codes, rule_names_by_code, veto_log)
      - selected_codes: 핸드오프 대상 종목코드(입력 순서 보존)
      - rule_names_by_code: {code: "ruleA,ruleB"} — 선정된 종목의 매칭 rule(legacy 는 빈 dict)
      - veto_log: [{code, name, rules:[...]}] — 제외된 종목·사유
    """
    if mode not in MODES:
        mode = "legacy"
    live_rules = live_rules or []
    veto_rules = veto_rules or []

    # ── veto: 모드 무관, 선정 직전 제외(reduce-only) ──
    vetoed: set = set()
    veto_log: list[dict] = []
    for c in candidates:
        hit = [r["name"] for r in veto_rules if _matches(r, c, market)]
        if hit:
            vetoed.add(_code(c))
            veto_log.append({"code": _code(c), "name": c.get("stock_name") or c.get("stk_nm"), "rules": hit})

    avail = [c for c in candidates if _code(c) not in vetoed]

    # ── legacy: 점수 rank ≤ top_n (rule 태깅 없음) ──
    if mode == "legacy":
        selected = [c for c in avail if _rank(c) <= top_n][:top_n]
        return [_code(c) for c in selected], {}, veto_log

    # ── hybrid / rules: live rule 매칭 계산 ──
    rule_names_by_code: dict[str, str] = {}
    matched: list[tuple[dict, float | None]] = []  # (candidate, best mean_net)
    for c in avail:
        hits = [r for r in live_rules if _matches(r, c, market)]
        if hits:
            rule_names_by_code[_code(c)] = ",".join(r["name"] for r in hits)
            matched.append((c, max((_mean_net(r) for r in hits), default=None)))

    if mode == "rules":
        # 기대값(mean_net) 순 — 결측/동률은 점수(rank)순. 상한 top_n. 매칭 0 = 무거래.
        matched.sort(key=lambda t: (-(t[1] if t[1] is not None else -1e9), _rank(t[0])))
        selected = [c for c, _ in matched][:top_n]
    else:  # hybrid: 매칭 우선(점수순) + 잔여 슬롯 미매칭 점수순
        prioritized = sorted((c for c, _ in matched), key=_rank)
        selected = prioritized[:top_n]
        if len(selected) < top_n:
            matched_codes = {_code(c) for c, _ in matched}
            fillers = sorted((c for c in avail if _code(c) not in matched_codes), key=_rank)
            selected += fillers[: top_n - len(selected)]

    selected_codes = [_code(c) for c in selected]
    sel_set = set(selected_codes)
    rule_names_by_code = {k: v for k, v in rule_names_by_code.items() if k in sel_set}
    return selected_codes, rule_names_by_code, veto_log
