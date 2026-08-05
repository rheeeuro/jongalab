"""선정 레이어 — 모드별 selected 판정 (순수 로직, DB·네트워크 무의존).

closing_bet 이 점수·rank_no·저장을 마친 뒤, 어떤 종목을 실매매로 핸드오프할지(selected)만
이 함수로 정한다. trading_engine(가드 파일)·점수 계산은 건드리지 않는다.

모드(EDGE_SELECTION_MODE):
  legacy : 점수 rank_no ≤ top_n (현행) — rule_names 없음(NULL)
  hybrid : **표 많은 종목 우선**(아래 우선순위), 총 상한 top_n
  rules  : live rule 매칭 합집합만(상한 초과 시 rule 기대값 mean_net 순). 매칭 0 = 무거래

hybrid 우선순위 (2026-08-05 사용자 결정 — 점수 의존을 걷어내고 rules 모드로 가는 중간 단계):
  ① **표 수** — 매칭된 live selector 개수 + (legacy 점수 top_n 안이면 1표).
     legacy 점수도 하나의 rule 로 취급해 특권을 없앤다(전에는 매칭 유무만 보고 나머지는 전부 점수순).
  ② 동표면 **성적** — 그 종목을 지목한 rule 중 최고 `stats.mean_net`(legacy 표는 `legacy_mean_net`).
  ③ 그래도 동률이거나 슬롯이 남으면 **legacy 점수**(rank_no).
근거와 한계(2026-08-05 실측, 7/7~8/4 20거래일 · exec_leg_ret · 비용 차감):
  - **표 수는 신호다**: 0표 승률 48.6%·일등가중 +0.447% → 3표 66.7%·+1.122% 로 단조 증가.
  - **표는 중복 셈이 아니다**: 2표 이상 161건 중 핵심 피처 컬럼(공통 필터 `change_pct` 제외)을
    공유하는 쌍이 낀 경우는 **0건**. 외인 서지 3종(carry/pullback1/supply_eagle)은 같은
    `days_since_frgn_surge` 를 보지만 조건이 배타적이라 동시 매칭이 불가능하다.
    ⚠️ 앞으로 **같은 피처에 문턱만 다른 룰**(예: afternoon_ret>=1.5 와 >=2.5)을 등록하면 그때부터
    한 축이 2표를 만든다 — 그런 쌍을 만들 땐 배타 조건으로 설계하거나 표 집계를 다시 볼 것.
  - ⚠️ **성과 개선 목적은 아니다**: 반사실에서 현행 +0.771%/일(t 1.25) vs 이 규칙 +0.706%(t 1.05)로
    사실상 동률이었다(그날 시점 성적 기준. 사후 stats 로 재면 +0.985% 로 보이지만 그건 lookahead).
    매칭 종목이 이미 슬롯의 2배(하루 21종 vs 10칸)라 바뀌는 게 내부 순서뿐이기 때문이다.

veto(감액·제외) rule 은 모드 무관하게 선정 직전 적용(reduce-only — 제외만, 승급 없음).

⚠️ 선정 시점(closing_bet 13~15시)엔 NXT 스냅샷(nxt_gap_pct 등)·당일 market_snapshot 이
아직 없다(19:50 수집). 그 컬럼을 참조하는 rule 은 predicate 상 NULL→매칭실패라 이 시점 선정에
기여하지 못한다(F1 뉴스·F4 섹터처럼 13~15시에 채워지는 피처 기반 rule 만 유효). 의도된 보수 동작.

DB 무의존 순수 함수 → tests/test_edge_selection.py 가 계약을 고정한다.
"""
from core.edge_predicate import evaluate

MODES = ("legacy", "hybrid", "rules")

# 성적 미상(stats.mean_net 결측)일 때 쓰는 정렬 하한 — 같은 표 수 안에서 성적이 있는 rule 뒤로
# 밀린다. 등록 직후라 표본이 없는 rule 이 무근거로 우대받지 않게 하려는 것.
_NO_STATS = float("-inf")


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
    legacy_mean_net: float | None = None,
) -> tuple[list[str], dict[str, str], list[dict]]:
    """모드별 selected 판정.

    candidates: 점수순(rank_no 오름차순) 정렬된 리포트 행 dict 목록.
    live_rules: role=selector 인 live rule dict 목록(name·predicate·stats). veto_rules: role=veto live rule.
    legacy_mean_net: hybrid 에서 'legacy 표'의 성적(② 동표 tie-break)으로 쓸 값 —
        대조군 benchmark(control_legacy_top10) 의 `stats.mean_net`. None 이면 성적 미상으로 보고
        같은 표 수 안에서 성적이 있는 rule 뒤로 밀린다(무근거 우대 방지).
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
    hits_by_code: dict[str, list[dict]] = {}
    matched: list[tuple[dict, float | None]] = []  # (candidate, best mean_net)
    for c in avail:
        hits = [r for r in live_rules if _matches(r, c, market)]
        if hits:
            hits_by_code[_code(c)] = hits
            rule_names_by_code[_code(c)] = ",".join(r["name"] for r in hits)
            matched.append((c, max((_mean_net(r) for r in hits), default=None)))

    if mode == "rules":
        # 기대값(mean_net) 순 — 결측/동률은 점수(rank)순. 상한 top_n. 매칭 0 = 무거래.
        matched.sort(key=lambda t: (-(t[1] if t[1] is not None else -1e9), _rank(t[0])))
        selected = [c for c, _ in matched][:top_n]
    else:  # hybrid: 표 수 → 성적 → 점수 (모듈 docstring 의 ①②③)
        def _priority(c: dict) -> tuple:
            hits = hits_by_code.get(_code(c), [])
            in_legacy = _rank(c) <= top_n
            perf = [m for m in ([_mean_net(r) for r in hits]
                                + ([legacy_mean_net] if in_legacy else [])) if m is not None]
            votes = len(hits) + (1 if in_legacy else 0)
            # 표 0(매칭도 legacy 도 아님)인 종목은 자연히 뒤로 밀려 '잔여 슬롯 점수순 채움'이 된다
            # — 별도 filler 단계가 필요 없다.
            return (-votes, -(max(perf) if perf else _NO_STATS), _rank(c))

        selected = sorted(avail, key=_priority)[:top_n]

    selected_codes = [_code(c) for c in selected]
    sel_set = set(selected_codes)
    rule_names_by_code = {k: v for k, v in rule_names_by_code.items() if k in sel_set}
    return selected_codes, rule_names_by_code, veto_log
