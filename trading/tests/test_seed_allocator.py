"""seed_allocator.allocate 골든 테스트 — 시드 배분(자금 분배)의 핵심 불변식 고정.

불변식:
  - 점수 가중 비례 배분 + 잔여 그리디 재투입으로 활용률 최대화(leftover < 최저가)
  - 총 매수금액(sum cost)은 seed 를 절대 초과하지 않는다
  - price<=0 / seed<=0 / total_score<=0 이면 배분하지 않는다
  - 순수함수(반복 호출 시 동일 결과, 내부 _alloc 키 누출 없음)
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
    cands = [
        {"stk_cd": "A", "score": 3, "price": 10000},
        {"stk_cd": "B", "score": 1, "price": 10000},
    ]
    allocate(1_000_000, cands)
    assert cands[0]["shares"] > cands[1]["shares"]
    assert cands[0]["shares"] == 75
    assert cands[1]["shares"] == 25


def test_leftover_greedy_reinvest_maximizes_utilization():
    # 30,000원 종목 2개에 100,000원 → 1차 비례로 1주씩(60,000) 후 그리디로 1주 추가
    cands = [
        {"stk_cd": "A", "score": 1, "price": 30000},
        {"stk_cd": "B", "score": 1, "price": 30000},
    ]
    allocate(100_000, cands)
    total_shares = cands[0]["shares"] + cands[1]["shares"]
    leftover = 100_000 - _total_cost(cands)
    assert total_shares == 3                 # 1+1 비례 + 1 그리디
    assert 0 <= leftover < 30000             # 더 못 사는 잔액만 남음(활용 최대)


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


def test_no_internal_alloc_key_leaks():
    cands = [{"stk_cd": "A", "score": 1, "price": 10000}]
    allocate(500_000, cands)
    assert "_alloc" not in cands[0]


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
