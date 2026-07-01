"""seed_allocator.allocate 골든 테스트 — 시드 배분(자금 분배)의 핵심 불변식 고정.

불변식(등가중):
  - 점수 상위 TOP_N(=10) 개만 배분 대상 (그 밖은 0주) — 선정 컷은 점수순
  - 선정된 종목엔 **등가중** 목표금액(seed/N) → 정수 주 내림(1차). 점수는 사이징에 무관
    (실거래상 점수가 익일 청산 손익을 예측 못 해 점수비례 집중을 제거함)
  - 잔여현금은 현재 투입액이 가장 적은 종목부터 채워 균형을 맞춘다(2차)
  - 종목당 투입은 시드의 MAX_NAME_PCT(=50%) 캡을 넘지 않는다(고정금액 아닌 시드 대비)
  - 총 매수금액(sum cost)은 seed 를 절대 초과하지 않는다
  - price<=0 / seed<=0 / 후보 없음이면 배분하지 않는다
  - 순수함수(반복 호출 시 동일 결과)
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


def test_equal_weight_ignores_score():
    # 등가중 → 점수가 달라도 (선정만 되면) 목표금액은 동일. 잔여 1주만 최소투입 우선.
    cands = [
        {"stk_cd": "A", "score": 5, "price": 10000},
        {"stk_cd": "B", "score": 4, "price": 10000},
        {"stk_cd": "C", "score": 3, "price": 10000},
    ]
    allocate(1_000_000, cands)
    a, b, c = cands
    # 1M/3=333,333 → 33주씩(990k), 잔여 10k 는 1주만 추가(동률 → 첫 종목 A)
    assert (a["shares"], b["shares"], c["shares"]) == (34, 33, 33)
    # 점수비례였다면 (42, 33, 25) 였을 것 — 더는 점수에 비례하지 않는다
    assert _total_cost(cands) == 1_000_000


def test_allocates_only_top_10_by_score():
    # 11개 후보 → 점수 최하위 1개는 시드가 충분해도 0주(상위 10개만 배분). 선정 컷은 점수순 유지.
    cands = [{"stk_cd": f"S{i}", "score": 100 - i, "price": 1000} for i in range(11)]
    allocate(10_000_000, cands)
    ranked = sorted(cands, key=lambda c: c["score"], reverse=True)
    assert all(c["shares"] > 0 for c in ranked[:10])
    assert ranked[10]["shares"] == 0 and ranked[10]["cost"] == 0


def test_leftover_greedy_reinvest_maximizes_utilization():
    # 동점 3종목(30,000원)에 300,000원 → 등가중 3주씩(270,000) 후 그리디로 1주 추가
    cands = [
        {"stk_cd": "A", "score": 1, "price": 30000},
        {"stk_cd": "B", "score": 1, "price": 30000},
        {"stk_cd": "C", "score": 1, "price": 30000},
    ]
    allocate(300_000, cands)
    total_shares = sum(c["shares"] for c in cands)
    leftover = 300_000 - _total_cost(cands)
    assert total_shares == 10                # 3+3+3 등가중 + 1 그리디
    assert 0 <= leftover < 30000             # 더 못 사는 잔액만 남음(활용 최대)


def test_leftover_balances_evenly_regardless_of_score():
    # 잔여현금은 '현재 투입액이 가장 적은' 종목부터 채운다 — 저점수 C 도 굶지 않고
    # 종목 간 배분이 최대 1주 차이로 균형을 이룬다(점수 우선 집중 제거).
    cands = [
        {"stk_cd": "A", "score": 10, "price": 10000},
        {"stk_cd": "B", "score": 9, "price": 10000},
        {"stk_cd": "C", "score": 1, "price": 10000},
    ]
    allocate(100_000, cands)
    a, b, c = cands
    assert c["shares"] == 3                              # 최저점도 등가중 배분(과거엔 0)
    assert max(x["shares"] for x in cands) - min(x["shares"] for x in cands) <= 1


def test_score_does_not_gate_allocation():
    # 점수 0(혹은 음수)이어도 선정되면 등가중 배분된다 — 사이징은 점수와 무관.
    cands = [
        {"stk_cd": "A", "score": 0, "price": 10000},
        {"stk_cd": "B", "score": -5, "price": 20000},
    ]
    allocate(1_000_000, cands)
    assert all(c["shares"] > 0 for c in cands)   # 과거엔 0점/음수는 배분 제외였음


def test_per_name_cost_capped_at_seed_pct():
    # 종목 수가 적어 등가중 목표(seed/N)가 캡을 넘어도, 종목당 투입은 시드의
    # MAX_NAME_PCT(=50%) 를 넘지 않는다. 단일 종목이면 시드 50%만 투입되고 나머지는 잔여.
    cands = [{"stk_cd": "A", "score": 100, "price": 10000}]
    allocate(1_000_000, cands)
    a = cands[0]
    assert a["cost"] == 500_000   # 시드의 50% 캡에서 정지
    assert _total_cost(cands) <= 1_000_000


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
