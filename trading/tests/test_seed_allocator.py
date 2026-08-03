"""seed_allocator.allocate 골든 테스트 — 시드 배분(자금 분배)의 핵심 불변식 고정.

불변식(확신도 등가중):
  - 점수 상위 TOP_N(=10) 개만 배분 대상 (그 밖은 0주) — 선정 컷은 점수순
  - 등가중 단위는 '종목'이 아니라 **선정 근거 1표**(`conviction`) — 표 비례 목표금액
    (seed×w/Σw) → 정수 주 내림(1차). `conviction` 없으면 전원 1표 = 종전 등가중과 동일.
    점수 '크기' 는 여전히 사이징에 무관(익일 손익 예측 실패 → 점수비례 집중 제거)
  - 표 수 상한은 CONVICTION_MAX_MULT, 종목당 캡(MAX_NAME_PCT)은 확신도와 무관하게 적용
  - 잔여현금은 **확신도 대비** 투입액(cost/w)이 가장 적은 종목부터 채워 표 비례를 맞춘다(2차)
  - 종목당 투입은 시드의 MAX_NAME_PCT(=25%, 2026-07-10 HLB 하한가 사건으로 50%→25%) 캡을
    넘지 않는다(고정금액 아닌 시드 대비). 캡이 시드 전량 투입보다 우선한다(잔여 현금 허용)
  - 예외: 주가가 캡을 넘는 고가주도 첫 1주는 cap×FIRST_SHARE_CAP_MULT(=2, 시드 50%)
    이내면 허용 — 1주가 최소 단위라 캡이 고가주를 통째로 걸러내면 분산이 줄기 때문.
    캡 초과 '누적 매수'(저가주가 잔여 현금을 흡수하는 HLB 패턴)는 어떤 경우에도 금지
  - 총 매수금액(sum cost)은 seed 를 절대 초과하지 않는다
  - price<=0 / seed<=0 / 후보 없음이면 배분하지 않는다
  - 순수함수(반복 호출 시 동일 결과)
"""
import pytest

import core.seed_allocator as seed_allocator
from core.seed_allocator import allocate, conviction_from_signal


@pytest.fixture(autouse=True)
def _pin_cap(monkeypatch):
    # .env 의 SEED_MAX_NAME_PCT 오버라이드와 무관하게 의도한 운영값(25%)으로 계약을 고정한다.
    monkeypatch.setattr(seed_allocator, "MAX_NAME_PCT", 0.25)
    monkeypatch.setattr(seed_allocator, "FIRST_SHARE_CAP_MULT", 2.0)
    monkeypatch.setattr(seed_allocator, "CONVICTION_MAX_MULT", 3.0)


def _total_cost(cands):
    return sum(c["cost"] for c in cands)


def test_equal_score_equal_price_splits_evenly():
    # 2종목이면 등가중 목표(50%)가 캡(25%)을 넘어 캡에서 정지 — 잔여 50%는 현금으로 남긴다.
    cands = [
        {"stk_cd": "A", "score": 1, "price": 10000},
        {"stk_cd": "B", "score": 1, "price": 10000},
    ]
    allocate(1_000_000, cands)
    assert cands[0]["shares"] == 25
    assert cands[1]["shares"] == 25
    assert _total_cost(cands) == 500_000


def test_equal_weight_ignores_score():
    # 등가중 → 점수가 달라도 (선정만 되면) 목표금액은 동일하고 캡(25%)에서 함께 정지한다.
    cands = [
        {"stk_cd": "A", "score": 5, "price": 10000},
        {"stk_cd": "B", "score": 4, "price": 10000},
        {"stk_cd": "C", "score": 3, "price": 10000},
    ]
    allocate(1_000_000, cands)
    a, b, c = cands
    # 목표 min(1M/3, 캡 250k)=250k → 25주씩. 점수비례였다면 고점수에 집중됐을 것.
    assert (a["shares"], b["shares"], c["shares"]) == (25, 25, 25)
    assert _total_cost(cands) == 750_000


def test_allocates_only_top_10_by_score():
    # 11개 후보 → 점수 최하위 1개는 시드가 충분해도 0주(상위 10개만 배분). 선정 컷은 점수순 유지.
    cands = [{"stk_cd": f"S{i}", "score": 100 - i, "price": 1000} for i in range(11)]
    allocate(10_000_000, cands)
    ranked = sorted(cands, key=lambda c: c["score"], reverse=True)
    assert all(c["shares"] > 0 for c in ranked[:10])
    assert ranked[10]["shares"] == 0 and ranked[10]["cost"] == 0


def test_leftover_greedy_reinvest_maximizes_utilization():
    # 캡이 안 묶이는 구간(5종목 → 등가중 20% < 캡 25%)에선 그리디가 잔여를 최대로 채운다.
    # 750k/5=150k 목표 → 4주(124k)씩(620k), 잔여 130k 를 최소투입 우선 1주씩(155k ≤ 캡 187.5k).
    cands = [{"stk_cd": f"S{i}", "score": 1, "price": 31000} for i in range(5)]
    allocate(750_000, cands)
    total_shares = sum(c["shares"] for c in cands)
    leftover = 750_000 - _total_cost(cands)
    assert total_shares == 24                # 4×5 등가중 + 4 그리디
    assert 0 <= leftover < 31000             # 더 못 사는 잔액만 남음(활용 최대)


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
    # 목표 min(33.3k, 캡 25k)=25k → 2주씩. 잔여 40k 는 캡 도달로 현금 잔류.
    assert c["shares"] == 2                              # 최저점도 등가중 배분(과거엔 0)
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
    # MAX_NAME_PCT(=25%) 를 넘지 않는다. 단일 종목이면 시드 25%만 투입되고 나머지는 잔여.
    cands = [{"stk_cd": "A", "score": 100, "price": 10000}]
    allocate(1_000_000, cands)
    a = cands[0]
    assert a["cost"] == 250_000   # 시드의 25% 캡에서 정지
    assert _total_cost(cands) <= 1_000_000


def test_cheap_stock_cannot_absorb_leftover_beyond_cap():
    # 2026-07-10 HLB 하한가 사건 재현 — 실제 7/9 NXT 시드·가격. 종전(캡 50%)엔 그리디가
    # 잔여 현금을 최저가 종목(HLB)에 몰아줘 7주(35%)가 됐다. 캡 25%면 5주(24.9%)에서 멈추고,
    # 고가주(삼성전자)는 첫 1주 예외로 살아남는다.
    cands = [
        {"stk_cd": "005930", "score": 43.5, "price": 283000},   # 삼성전자
        {"stk_cd": "105560", "score": 41.5, "price": 171900},   # KB금융
        {"stk_cd": "042700", "score": 40.0, "price": 220500},   # 한미반도체
        {"stk_cd": "028300", "score": 38.6, "price": 52600},    # HLB
    ]
    seed = 1_054_869
    allocate(seed, cands)
    by_cd = {c["stk_cd"]: c for c in cands}
    assert by_cd["028300"]["shares"] == 5                       # 실사고 당시엔 7주였다
    assert by_cd["028300"]["cost"] <= seed * 0.25
    assert by_cd["005930"]["shares"] == 1                       # 첫 1주 예외로 포함 유지
    assert _total_cost(cands) <= seed


def test_first_share_allowed_above_cap_within_mult():
    # 주가가 캡(25%)을 넘지만 캡×2(=시드 50%) 이내인 고가주는 첫 1주만 허용된다.
    cands = [
        {"stk_cd": "A", "score": 2, "price": 400_000},
        {"stk_cd": "B", "score": 1, "price": 10_000},
    ]
    allocate(1_000_000, cands)
    a, b = cands
    assert a["shares"] == 1        # 250k < 400k <= 500k → 1주 예외
    assert a["cost"] == 400_000
    assert b["cost"] <= 250_000    # 저가주는 캡 준수


def test_first_share_blocked_beyond_mult_cap():
    # 캡×2(=시드 50%)를 넘는 초고가주는 1주도 배분하지 않는다 — 단일 종목 노출 상한.
    cands = [
        {"stk_cd": "A", "score": 2, "price": 600_000},
        {"stk_cd": "B", "score": 1, "price": 10_000},
    ]
    allocate(1_000_000, cands)
    assert cands[0]["shares"] == 0 and cands[0]["cost"] == 0


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


def test_conviction_scales_target_amount():
    # 근거 2표 종목(A)은 1표 종목보다 목표금액이 2배 — 8종목이라 캡(25%)에 안 걸리는 구간.
    # 표 합 9 → A 목표 seed×2/9=222k(22주), 나머지 111k(11주). 잔여는 표 대비 투입이 가장
    # 적은 A 로 흘러 23주. (등가중이었다면 전원 12주 근처였을 것)
    cands = [{"stk_cd": f"S{i}", "score": 1, "price": 10_000,
              "conviction": 2 if i == 0 else 1} for i in range(8)]
    allocate(1_000_000, cands)
    a, rest = cands[0], cands[1:]
    assert a["shares"] == 23
    assert all(c["shares"] == 11 for c in rest)
    assert _total_cost(cands) <= 1_000_000


def test_missing_conviction_is_equal_weight():
    # conviction 키가 없으면 전원 1표 — 종전 등가중 결과와 완전히 같아야 한다(회귀 방지).
    def fresh(with_conv):
        return [{"stk_cd": f"S{i}", "score": 10 - i, "price": 7_000,
                 **({"conviction": 1} if with_conv else {})} for i in range(6)]
    plain, ones = fresh(False), fresh(True)
    allocate(500_000, plain)
    allocate(500_000, ones)
    assert [c["shares"] for c in plain] == [c["shares"] for c in ones]


def test_conviction_clamped_at_max_mult(monkeypatch):
    # 표가 10개여도 CONVICTION_MAX_MULT(=3) 배까지만 실어준다. 캡을 풀어 클램프만 본다.
    monkeypatch.setattr(seed_allocator, "MAX_NAME_PCT", 1.0)
    cands = [{"stk_cd": f"S{i}", "score": 1, "price": 10_000,
              "conviction": 10 if i == 0 else 1} for i in range(4)]
    allocate(1_000_000, cands)
    # 클램프 3 → 표합 6 → A 목표 500k(50주). 클램프가 없었다면 표합 13 → 76주였다.
    assert cands[0]["shares"] == 50


def test_conviction_cannot_break_per_name_cap():
    # 확신도가 높아도 종목당 캡(시드 25%)은 그대로다 — 하한가 1방 손실 봉쇄는 캡만이 한다.
    cands = [
        {"stk_cd": "A", "score": 2, "price": 10_000, "conviction": 3},
        {"stk_cd": "B", "score": 1, "price": 10_000, "conviction": 1},
    ]
    allocate(1_000_000, cands)
    assert cands[0]["cost"] <= 250_000


def test_leftover_greedy_follows_conviction(monkeypatch):
    # 잔여 재투입은 '투입액'이 아니라 '표 대비 투입액(cost/w)'이 가장 적은 종목으로 간다.
    # 표 2:1 → 목표 66.6k(6주)/33.3k(3주), 잔여 10k. 종전(원시 cost 기준)이면 투입이 적은
    # B 가 받아 6:4 가 됐겠지만, 표 대비로는 동률이라 안정 정렬로 A(상위) 가 받아 7:3 이 된다.
    monkeypatch.setattr(seed_allocator, "MAX_NAME_PCT", 1.0)
    cands = [
        {"stk_cd": "A", "score": 2, "price": 10_000, "conviction": 2},
        {"stk_cd": "B", "score": 1, "price": 10_000, "conviction": 1},
    ]
    allocate(100_000, cands)
    assert (cands[0]["shares"], cands[1]["shares"]) == (7, 3)


def test_conviction_counts_rules_plus_legacy_score():
    # 표 = 매칭 rule 수 + legacy 점수 1표(점수 top-N 에도 들었으면). 최소 1.
    assert conviction_from_signal({"rule_names": None, "rank_no": 3}, 10) == 1      # 점수만
    assert conviction_from_signal({"rule_names": "a,b", "rank_no": 15}, 10) == 2    # rule 2개
    assert conviction_from_signal({"rule_names": "a,b", "rank_no": 3}, 10) == 3     # rule 2 + 점수
    assert conviction_from_signal({"rule_names": "a", "rank_no": None}, 10) == 1    # rank 모름
    assert conviction_from_signal({"rule_names": "a,b", "rank_no": 3}, None) == 2   # N 모름=보수적
    assert conviction_from_signal({"rule_names": "a,a", "rank_no": 15}, 10) == 1    # 중복 태그 1표
    assert conviction_from_signal({}, None) == 1                                    # 재료 없음


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
