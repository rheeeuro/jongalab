"""시드 배분기 — 종가랩 종목탭 SeedAllocator 와 동일한 배분 로직.

점수 상위 TOP_N 개 후보만 대상으로, 점수에 비례해 목표 금액을 잡아 정수 주식으로
내림 배분한 뒤(1차), 잔여 현금을 그리디로 재투입한다(2차). 2차는 점수가 가장 큰
종목부터 1주씩 추가 매수해, 확신 높은 상위 종목에 자본을 집중시킨다. 단 한 종목
투입은 시드의 MAX_NAME_PCT 비율을 넘지 않도록 캡을 둬(고정금액이 아닌 시드 대비),
과집중을 막는다.

allocate(seed, candidates):
  candidates: [{"stk_cd", "score", "price"} ...]  (price<=0 이면 배분 0)
  반환: 동일 리스트에 "shares", "cost" 추가 (상위 TOP_N 밖 / 무효가는 0)
"""

from core.config import SEED_MAX_NAME_PCT

# 배분 대상 후보 수 상한 — 점수 상위 N개만 매수
TOP_N = 10
# 종목당 최대 투입 비율은 .env(→ core.config) 로 튜닝한다.
MAX_NAME_PCT = SEED_MAX_NAME_PCT


def allocate(seed: int, candidates: list[dict]) -> list[dict]:
    for c in candidates:
        c.setdefault("shares", 0)
        c.setdefault("cost", 0)

    # 유효가(>0) 후보를 점수순으로 정렬해 상위 TOP_N 개만 배분 대상으로 삼는다.
    priced = [c for c in candidates if (c.get("price") or 0) > 0]
    priced.sort(key=lambda c: max(c.get("score") or 0, 0), reverse=True)
    items = priced[:TOP_N]

    for c in items:
        c["_w"] = max(c.get("score") or 0, 0)   # 가중치 = 점수(음수는 0 클램프)
    total_w = sum(c["_w"] for c in items)
    if seed <= 0 or not items or total_w <= 0:
        for c in items:
            c.pop("_w", None)
        return candidates

    # 종목당 최대 투입금액 — 시드 대비 비율 캡(이 금액을 넘게는 배분하지 않는다).
    cap = seed * MAX_NAME_PCT

    # 1차: weight 비례 목표금액(캡 적용) → 정수 주식 내림 배분
    for c in items:
        target = min(seed * c["_w"] / total_w, cap)
        c["shares"] = int(target // c["price"])
        c["cost"] = c["shares"] * c["price"]

    # 2차: 잔여 현금 그리디 재투입 — weight(점수)가 가장 큰 종목부터 1주씩 추가 매수.
    #   확신 높은 상위 종목에 자본을 집중시킨다(비례 분산이 아니라 상위 우선). 단 한 주 더
    #   사면 종목당 캡(cap)을 넘는 종목은 제외하므로, 1등이 캡에 닿으면 잔여는 다음 상위
    #   종목으로 흐른다. 매수 가능 종목이 없을 때까지(잔여 < 최저가 또는 전원 캡 도달) 채운다.
    leftover = seed - sum(c["cost"] for c in items)
    while True:
        best = None
        best_w = float("-inf")
        for c in items:
            if c["_w"] <= 0:  # 0점(음수) 종목엔 잔여현금도 배분하지 않는다
                continue
            if c["price"] <= 0 or c["price"] > leftover:
                continue
            if c["cost"] + c["price"] > cap:
                continue
            if c["_w"] > best_w:
                best_w = c["_w"]
                best = c
        if best is None:
            break
        best["shares"] += 1
        best["cost"] += best["price"]
        leftover -= best["price"]

    for c in items:
        c.pop("_w", None)
    return candidates
