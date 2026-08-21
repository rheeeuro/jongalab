"""집행 레이어 rule 평가 — NXT 19:50 데드라인에서 '이 종목을 살지'를 원장으로 판정한다.

순수 로직(DB·네트워크 무의존) → tests/test_edge_execution.py 가 계약을 고정한다.
DB 조회는 `core/repository/edge_rule.py`, 갭 계산·주문은 `workers/signal_executor.py`.

## 왜 집행 레이어에 rule 이 있는가
NXT 야간 갭(`nxt_gap_pct` = (NXT 현재가 − KRX 확정 종가)/KRX 종가)은 **19:50 주문 직전에만**
알 수 있다. NXT 매수는 그 시각 단일 주문이고 신호 핸드오프(19:40)·시드 배분은 그보다 앞선다.
그래서 이 값을 쓰는 rule 은 선정 레이어(jongalab `edge_selection`)에서 영원히 NULL→무음이다.
원장 밖 하드코딩으로 집행하면 채점·강등 감시가 사라지므로(2026-08-03 그렇게 했다가 되돌림)
집행기가 원장 predicate 를 그 시점 갭으로 평가한다. 채점(jongalab rule_evaluator)이 쓰는
`nxt_gap_pct` 는 gap_check(19:50)가 같은 정의로 기록한 값이라 **집행 값과 같은 변수**다 —
rule 의 과거 stats 를 승격 근거로 그대로 쓸 수 있는 이유이자, 이 설계의 핵심 전제다.

## 두 가지 제약 (설계상 반드시 지킬 것)
1. **종목을 추가하지 못한다.** 후보 풀·시드 배분이 19:40 에 확정된 뒤라 빈 슬롯을 채울 대상이
   없다. role=selector 여도 실효 의미는 "이미 선정된 종목 중 매칭분만 매수"다(reduce-only).
   → 거른 몫의 시드는 **논다**(하이브리드 대체 불가). 기대효과를 잴 때 이게 전제다.
2. **적용 대상은 그 rule 이 혼자 데려온 종목뿐이다**(2026-08-03 사용자 결정, `in_scope` 참조).
   다른 rule 과 함께 선정 / 점수 top-N 에도 포함 / 점수순으로만 선정 → 전부 비대상.
   "이 rule 때문에 들어온 종목만 이 rule 로 재확인한다"는 규율이다.
   ⚠️ 이 범위는 **미측정**이다: 세션 실측 +0.557%p(t=1.12)는 선정된 NXT **전체**를 거른
   결과이고, 단독 선정분만 거르는 범위는 표본이 훨씬 좁아 소급 측정이 불가하다. 근거는
   '가장 보수적'이라는 것뿐 — 실제 성적은 live rule 채점·강등 감시가 판정한다.
"""
from core.edge_predicate import evaluate, PredicateError

# 집행 레이어에서 평가할 수 있는 컬럼 — jongalab `edge_policy.EXECUTION_TIME_COLS` 와 같은 뜻.
# 여기서 다시 화이트리스트를 두지 않는 이유: 두 곳이 어긋나면 "승격은 됐는데 집행기가 평가를
# 건너뛰는" 조용한 무음이 생긴다. 대신 **집행기가 채워주는 컬럼만** 명시한다(아래 EXEC_FILLED).
# 그 밖의 컬럼은 daily_stock_report 행에 이미 있는 값을 그대로 쓴다.
EXEC_FILLED_COLS: frozenset[str] = frozenset({"nxt_gap_pct", "nxt_price_1950"})


def _needs_market(rule: dict) -> bool:
    """predicate 가 시황 축(`market.*`)을 요구하는가 — 집행기가 공급할 수 없는 재료다."""
    return any(str(c.get("col", "")).startswith("market.")
               for c in (rule.get("predicate") or []) if isinstance(c, dict))


def is_execution_layer_rule(rule: dict) -> bool:
    """이 live rule 을 집행 레이어에서 평가해야 하는가.

    판정 기준은 **집행기가 채워주는 컬럼을 predicate 가 쓰는지**다. 선정 레이어에서 이미
    평가 가능한 rule(수급·차트·공시 등)은 거기서 동작하므로 집행기가 손대지 않는다 —
    두 레이어가 같은 rule 을 이중으로 적용하면 선정에서 통과한 종목을 집행에서 또 거른다.
    """
    cols = {c.get("col") for c in (rule.get("predicate") or []) if isinstance(c, dict)}
    return bool(cols & EXEC_FILLED_COLS)


def in_scope(rule_names: str | None, exec_rule_names: list[str],
             rank_no: int | None, score_top_n: int | None) -> tuple[bool, str]:
    """이 종목이 집행 레이어 판정 **대상**인지. 반환: (대상 여부, 사유).

    대상은 **집행 레이어 rule 이 혼자 데려온 종목**뿐이다(2026-08-03 사용자 결정):
      · 다른 rule 과 함께 선정 → 비대상(그 rule 이 별도 근거를 갖는다)
      · 점수 top-N 에도 들었음 → 비대상(룰이 없어도 선정될 종목이었다)
      · 점수순으로만 선정 → 비대상(하이브리드의 '잔여 슬롯은 점수순'을 집행이 뒤집지 않는다)
    즉 "이 rule 때문에 들어온 종목만 이 rule 로 재확인한다". 그 밖은 전부 매수.

    rank_no/score_top_n 이 없으면 점수 판정을 못 하므로 **대상에서 뺀다**(보수적 — 판정 불가는
    매수 쪽으로 흘린다). score_top_n 은 그날 선정 종목 수로 근사한다(호출부 참조).
    """
    tags = [t for t in (rule_names or "").split(",") if t.strip()]
    if not tags:
        return False, "점수 선정분 — 필터 대상 아님(하이브리드 잔여 슬롯 존중)"
    if len(tags) > 1:
        return False, f"다른 rule 과 함께 선정({','.join(tags)}) — 필터 대상 아님"
    if tags[0] not in exec_rule_names:
        return False, f"선정 근거가 집행 레이어 rule 이 아님({tags[0]}) — 필터 대상 아님"
    if rank_no is None or score_top_n is None:
        return False, "점수 순위 판정 불가 — 필터 대상 아님(보수적)"
    if rank_no <= score_top_n:
        return False, f"점수 top-{score_top_n} 에도 포함(rank {rank_no}) — 필터 대상 아님"
    return True, f"{tags[0]} 단독 선정(rank {rank_no} > top-{score_top_n}) — 판정 대상"


def decide(report_row: dict | None, live_rules: list[dict], nxt_gap_pct: float | None,
           nxt_price: int | None, rule_names: str | None = None,
           rank_no: int | None = None, score_top_n: int | None = None) -> dict:
    """이 종목을 살지 판정. 반환:
      {"buy": bool, "in_scope": bool, "matched": [rule name...], "evaluated": [rule name...],
       "reason": str}

    report_row  : jongalab daily_stock_report 행(dict) 또는 None(행 없음)
    live_rules  : status='live' rule 목록(집행 레이어 rule 이 없으면 무개입)
    nxt_gap_pct : 주문 직전 계산한 갭(%). None 이면 판정 불가
    rule_names  : trade_signal.rule_names (선정 근거 rule name 콤마 목록, 점수 선정은 None)
    rank_no/score_top_n : 점수 순위와 그날 선정 종목 수 — '점수로도 들어왔는가' 판정용

    **fail-open 규약**: 집행 레이어 rule 이 없거나 / 판정 대상이 아니거나(위 in_scope) /
    갭·행·predicate 어디든 재료가 없으면 **매수**한다. 미검증 후보급 판정이라 데이터 결함으로
    매수가 조용히 멈추는 게 더 나쁘고, 선물·거시 감액 게이트가 미개입으로 폴백하는 규약과 같다.
    """
    exec_rules = [r for r in (live_rules or []) if is_execution_layer_rule(r)]
    if not exec_rules:
        return {"buy": True, "in_scope": False, "matched": [], "evaluated": [],
                "reason": "집행 레이어 live rule 없음 — 무개입"}
    names = [r.get("name") for r in exec_rules]
    scoped, why = in_scope(rule_names, names, rank_no, score_top_n)
    if not scoped:
        return {"buy": True, "in_scope": False, "matched": [], "evaluated": names,
                "reason": why}
    if nxt_gap_pct is None or not report_row:
        return {"buy": True, "in_scope": True, "matched": [], "evaluated": names,
                "reason": "판정 불가(갭 또는 리포트 행 없음) — fail-open 매수"}

    # 집행 시점 값으로 행을 덮어쓴다. 원본 dict 를 건드리지 않는다(호출부가 재사용할 수 있다).
    row = {**report_row, "nxt_gap_pct": nxt_gap_pct}
    if nxt_price:
        row["nxt_price_1950"] = nxt_price

    matched = []
    for r in exec_rules:
        if _needs_market(r):
            # 시황 축(`market.*`)을 쓰는 rule — 집행기는 시장 스냅샷을 갖지 않는다(그 축은
            # jongalab 선정 회차 19:40 이 슬롯 1935 로 평가한다). 여기서 평가하면 NULL 매칭
            # 실패가 되고, 이 레이어는 미매칭이 곧 매수 스킵이라 **조용히 전건 거부**된다.
            # 판정 불가는 매수 쪽으로 흘린다(모듈 fail-open 규약).
            return {"buy": True, "in_scope": True, "matched": [], "evaluated": names,
                    "reason": f"판정 불가(시황 축은 집행기가 못 읽는다: {r.get('name')}) "
                              "— fail-open 매수"}
        try:
            if evaluate(r.get("predicate") or [], row, None):
                matched.append(r.get("name"))
        except PredicateError:
            # 오설정 rule 하나가 전 종목 매수를 막지 않는다 — 그 rule 만 무시(fail-open).
            continue
    if matched:
        return {"buy": True, "in_scope": True, "matched": matched, "evaluated": names,
                "reason": f"집행 레이어 rule 매칭: {','.join(matched)}"}
    return {"buy": False, "in_scope": True, "matched": [], "evaluated": names,
            "reason": f"집행 레이어 rule 전부 미매칭({','.join(names)}) — 매수 스킵"}
