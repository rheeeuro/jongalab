"""seed_allocator.allocate 골든 테스트 — 시드 배분(자금 분배)의 핵심 불변식 고정.

불변식:
  - 점수 상위 TOP_N(=10) 개만 배분 대상 (그 밖은 0주)
  - 점수 비례 가중 배분 → 정수 주 내림(1차)
  - 잔여현금은 weight(점수) 큰 종목부터 채워 상위에 집중(2차). 1등이 캡에 닿으면
    다음 상위로 흐른다. 저점수·고가 종목이 1등보다 많이 매수하던 역전을 방지한다.
  - 종목당 투입은 시드의 MAX_NAME_PCT(=50%) 캡을 넘지 않는다(고정금액 아닌 시드 대비)
  - 0점(음수) 종목은 1차·2차 모두에서 배분 제외(잔여현금도 못 받음)
  - 총 매수금액(sum cost)은 seed 를 절대 초과하지 않는다
  - price<=0 / seed<=0 / total_weight<=0 이면 배분하지 않는다
  - 순수함수(반복 호출 시 동일 결과, 내부 _w 키 누출 없음)
"""
from core.seed_allocator import allocate


def _total_cost(cands):
    return sum(c["cost"] for c in cands)


def test_equal_score_equal_price_splits_evenly():
    cands = [
        {"stk_cd": "A", "score": 1, "price": 10000},
        {"stk_cd": "B", "score": 1, "price": 10000},
    ]
    allocate(1_000_000, cands)
    assert cands[0]["shares"] == 50
    assert cands[1]["shares"] == 50
    assert _total_cost(cands) == 1_000_000


def test_higher_score_gets_more_shares():
    # 점수 비례 → 점수 높을수록 더 많은 주 (캡 비구속: 최상위도 시드 50% 미만)
    cands = [
        {"stk_cd": "A", "score": 5, "price": 10000},
        {"stk_cd": "B", "score": 4, "price": 10000},
        {"stk_cd": "C", "score": 3, "price": 10000},
    ]
    allocate(1_000_000, cands)
    a, b, c = cands
    assert a["shares"] > b["shares"] > c["shares"]
    # 잔여현금이 최상위 A 로 집중(점수 우선 2차)
    assert (a["shares"], b["shares"], c["shares"]) == (42, 33, 25)


def test_allocates_only_top_10_by_score():
    # 11개 후보 → 점수 최하위 1개는 시드가 충분해도 0주(상위 10개만 배분)
    cands = [{"stk_cd": f"S{i}", "score": 100 - i, "price": 1000} for i in range(11)]
    allocate(10_000_000, cands)
    ranked = sorted(cands, key=lambda c: c["score"], reverse=True)
    assert all(c["shares"] > 0 for c in ranked[:10])
    assert ranked[10]["shares"] == 0 and ranked[10]["cost"] == 0


def test_leftover_greedy_reinvest_maximizes_utilization():
    # 동점 3종목(30,000원)에 300,000원 → 비례 3주씩(270,000) 후 그리디로 1주 추가
    cands = [
        {"stk_cd": "A", "score": 1, "price": 30000},
        {"stk_cd": "B", "score": 1, "price": 30000},
        {"stk_cd": "C", "score": 1, "price": 30000},
    ]
    allocate(300_000, cands)
    total_shares = sum(c["shares"] for c in cands)
    leftover = 300_000 - _total_cost(cands)
    assert total_shares == 10                # 3+3+3 비례 + 1 그리디
    assert 0 <= leftover < 30000             # 더 못 사는 잔액만 남음(활용 최대)


def test_leftover_prioritizes_higher_score_over_lower():
    # 잔여현금은 priority(weight 기준) 높은 종목부터 채운다 — 최저점 C 는 굶고,
    # 상위 A·B 가 종목당 캡(시드 50%)까지 채워진다. (저점수 종목이 상위보다 많이
    # 매수하던 역전 회귀 방지)
    cands = [
        {"stk_cd": "A", "score": 10, "price": 10000},
        {"stk_cd": "B", "score": 9, "price": 10000},
        {"stk_cd": "C", "score": 1, "price": 10000},
    ]
    allocate(100_000, cands)
    a, b, c = cands
    assert c["shares"] == 0                              # 최저점은 잔여도 못 받음
    assert a["cost"] == 50_000 and b["cost"] == 50_000   # 종목당 캡 50%


def test_per_name_cost_capped_at_seed_pct():
    # 한 종목 점수가 압도적이어도 종목당 투입은 시드의 MAX_NAME_PCT(=50%) 를 넘지 않는다
    cands = [
        {"stk_cd": "A", "score": 100, "price": 10000},
        {"stk_cd": "B", "score": 1, "price": 10000},
    ]
    allocate(1_000_000, cands)
    a = next(c for c in cands if c["stk_cd"] == "A")
    assert a["cost"] <= 500_000   # 시드의 50% 캡


def test_never_exceeds_seed():
    cands = [
        {"stk_cd": "A", "score": 5, "price": 33333},
        {"stk_cd": "B", "score": 2, "price": 17777},
        {"stk_cd": "C", "score": 1, "price": 9999},
    ]
    allocate(500_000, cands)
    assert _total_cost(cands) <= 500_000


def test_zero_price_candidate_gets_nothing():
    cands = [
        {"stk_cd": "A", "score": 1, "price": 0},
        {"stk_cd": "B", "score": 1, "price": 10000},
    ]
    allocate(500_000, cands)
    assert cands[0]["shares"] == 0 and cands[0]["cost"] == 0
    assert cands[1]["shares"] > 0


def test_negative_price_treated_as_unpriced():
    cands = [{"stk_cd": "A", "score": 1, "price": -100}]
    allocate(500_000, cands)
    assert cands[0]["shares"] == 0 and cands[0]["cost"] == 0


def test_zero_seed_allocates_nothing():
    cands = [{"stk_cd": "A", "score": 1, "price": 10000}]
    allocate(0, cands)
    assert cands[0]["shares"] == 0 and cands[0]["cost"] == 0


def test_zero_total_score_allocates_nothing():
    cands = [
        {"stk_cd": "A", "score": 0, "price": 10000},
        {"stk_cd": "B", "score": 0, "price": 20000},
    ]
    allocate(1_000_000, cands)
    assert all(c["shares"] == 0 for c in cands)


def test_negative_score_clamped_not_crashing():
    # 음수 점수는 0 으로 클램프되어 배분에서 제외, 양수 점수만 배분
    cands = [
        {"stk_cd": "A", "score": -5, "price": 10000},
        {"stk_cd": "B", "score": 2, "price": 10000},
    ]
    allocate(500_000, cands)
    assert cands[0]["shares"] == 0
    assert cands[1]["shares"] > 0


def test_no_internal_weight_key_leaks():
    cands = [{"stk_cd": "A", "score": 1, "price": 10000}]
    allocate(500_000, cands)
    assert "_w" not in cands[0]


def test_idempotent_on_repeated_calls():
    def fresh():
        return [
            {"stk_cd": "A", "score": 3, "price": 12000},
            {"stk_cd": "B", "score": 1, "price": 8000},
        ]
    once = fresh()
    allocate(777_000, once)

    twice = fresh()
    allocate(777_000, twice)
    allocate(777_000, twice)  # 두 번 호출해도 동일 결과여야 한다

    assert [c["shares"] for c in once] == [c["shares"] for c in twice]
    assert [c["cost"] for c in once] == [c["cost"] for c in twice]
