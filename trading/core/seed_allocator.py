"""시드 배분기 — 종가랩 종목탭 SeedAllocator 와 동일한 배분 로직.

점수 가중 비례로 목표 금액을 잡아 정수 주식으로 배분한 뒤, 잔여 현금을
그리디(목표 대비 가장 덜 채워진 종목 우선)로 재투입해 활용률을 최대화한다.

allocate(seed, candidates):
  candidates: [{"stk_cd", "score", "price"} ...]  (price<=0 이면 배분 0)
  반환: 동일 리스트에 "shares", "cost" 추가
"""


def allocate(seed: int, candidates: list[dict]) -> list[dict]:
    for c in candidates:
        c.setdefault("shares", 0)
        c.setdefault("cost", 0)

    items = [c for c in candidates if (c.get("price") or 0) > 0]
    total_score = sum(max(c.get("score") or 0, 0) for c in items)
    if seed <= 0 or not items or total_score <= 0:
        return candidates

    # 1차: 점수 가중치로 목표 금액 → 정수 주식 비례 배분
    for c in items:
        weight = max(c.get("score") or 0, 0) / total_score
        c["_alloc"] = seed * weight                 # 목표 금액
        c["shares"] = int(c["_alloc"] // c["price"])
        c["cost"] = c["shares"] * c["price"]

    # 2차: 잔여 현금 그리디 재투입 (목표 대비 부족분이 큰 종목 우선)
    leftover = seed - sum(c["cost"] for c in items)
    while True:
        best = None
        best_gap = float("-inf")
        for c in items:
            if c["price"] <= 0 or c["price"] > leftover:
                continue
            gap = c["_alloc"] - c["cost"]
            if gap > best_gap:
                best_gap = gap
                best = c
        if best is None:
            break
        best["shares"] += 1
        best["cost"] += best["price"]
        leftover -= best["price"]

    for c in items:
        c.pop("_alloc", None)
    return candidates
