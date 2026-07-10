"""시드 배분기 — 종가랩 종목탭 SeedAllocator(프리뷰) 와 동일한 배분 로직.

점수 상위 TOP_N 개 후보만 대상으로(선정은 점수순), **선정된 종목엔 등가중**으로 목표
금액을 잡아 정수 주식으로 내림 배분한 뒤(1차), 잔여 현금을 그리디로 재투입한다(2차).
2차는 현재 투입액이 가장 적은 종목부터 1주씩 추가 매수해 배분을 균형 있게 채운다. 단
한 종목 투입은 시드의 MAX_NAME_PCT 비율을 넘지 않도록 캡을 둬(고정금액이 아닌 시드 대비),
과집중을 막는다. 하한가에선 손절이 물리적으로 불가하므로(2026-07-10 HLB 사건: 저가주가
잔여 현금을 흡수해 시드 35% → 하한가 1방에 포트 -8%) 최악 단일 종목 손실은 이 캡으로만
봉쇄된다. 예외로 **첫 1주**는 캡을 넘어도 시드의 FIRST_SHARE_CAP_MULT×캡까지 허용한다 —
1주가 최소 매매 단위라 고가주(삼성전자 등)를 캡이 통째로 걸러내면 분산이 오히려 줄기
때문이다(캡 초과 '누적 매수'만 금지되고, 시드가 커지면 예외는 자연히 무의미해진다).

[등가중 근거] 실거래 표본 분석 결과 종합점수는 종가베팅 익일 청산 손익을 예측하지
못했다(점수↔손익 음의 상관). 점수비례·상위집중 사이징은 '지는 고점수 종목'에 자본을
더 실어 변동성만 키웠다. 그래서 사이징에서 점수 tilt 를 제거하고 등가중으로 분산한다
(선정 컷은 여전히 점수순 TOP_N — 사이징만 등가중). 점수 예측력이 회복되면 재검토.

allocate(seed, candidates):
  candidates: [{"stk_cd", "score", "price"} ...]  (price<=0 이면 배분 0)
  반환: 동일 리스트에 "shares", "cost" 추가 (상위 TOP_N 밖 / 무효가는 0)
"""

from core.config import SEED_MAX_NAME_PCT

# 배분 대상 후보 수 상한 — 점수 상위 N개만 매수
TOP_N = 10
# 종목당 최대 투입 비율은 .env(→ core.config) 로 튜닝한다.
MAX_NAME_PCT = SEED_MAX_NAME_PCT
# 첫 1주 예외 상한 배수 — 주가가 캡×이 배수 이내인 고가주는 1주까지만 캡 초과를 허용.
# (기본 캡 25% × 2 = 시드 50%: 캡 강화 전의 단일 종목 상한과 같아 고가주 포함 범위는 유지)
FIRST_SHARE_CAP_MULT = 2.0


def allocate(seed: int, candidates: list[dict]) -> list[dict]:
    for c in candidates:
        c.setdefault("shares", 0)
        c.setdefault("cost", 0)

    # 유효가(>0) 후보를 점수순으로 정렬해 상위 TOP_N 개만 배분 대상으로 삼는다.
    priced = [c for c in candidates if (c.get("price") or 0) > 0]
    priced.sort(key=lambda c: max(c.get("score") or 0, 0), reverse=True)
    items = priced[:TOP_N]

    # 등가중: 선정된 종목엔 동일 목표금액. (점수는 선정 컷에만 쓰고 사이징엔 안 씀)
    n = len(items)
    if seed <= 0 or n == 0:
        return candidates

    # 종목당 최대 투입금액 — 시드 대비 비율 캡(이 금액을 넘게는 배분하지 않는다).
    cap = seed * MAX_NAME_PCT

    # 1차: 등가중 목표금액(캡 적용) → 정수 주식 내림 배분
    for c in items:
        target = min(seed / n, cap)
        c["shares"] = int(target // c["price"])
        c["cost"] = c["shares"] * c["price"]

    # 2차: 잔여 현금 그리디 재투입 — 현재 투입액이 가장 적은 종목부터 1주씩 추가 매수해
    #   배분을 균형 있게 채운다(등가중이라 상위 집중이 아니라 최소 투입 우선). 한 주 더 사면
    #   종목당 캡(cap)을 넘는 종목은 제외하며, 매수 가능 종목이 없을 때까지(잔여 < 최저가
    #   또는 전원 캡 도달) 채운다. 동률이면 items 순서(=점수순)로 안정 정렬된다.
    #   예외: 1주가 최소 매매 단위라, 주가가 캡을 넘는 고가주도 **첫 1주**는
    #   cap×FIRST_SHARE_CAP_MULT 이내면 허용한다(누적 매수로 캡을 넘는 건 계속 금지).
    leftover = seed - sum(c["cost"] for c in items)
    first_share_cap = cap * FIRST_SHARE_CAP_MULT
    while True:
        best = None
        best_cost = float("inf")
        for c in items:
            if c["price"] <= 0 or c["price"] > leftover:
                continue
            if c["cost"] + c["price"] > cap and not (
                c["shares"] == 0 and c["price"] <= first_share_cap
            ):
                continue
            if c["cost"] < best_cost:
                best_cost = c["cost"]
                best = c
        if best is None:
            break
        best["shares"] += 1
        best["cost"] += best["price"]
        leftover -= best["price"]

    return candidates
