"""시드 배분기 — 자동매수(signal_executor)·`/buy-preview` 의 종목별 금액 배분.

(종가랩 종목탭의 `SeedAllocator.tsx` 는 사람이 금액을 넣어보는 **수동 계산기**로 캡·확신도
없이 등가중만 쓴다 — 같은 뼈대에서 나왔지만 이제 이 파일과 같은 로직이 아니다.)

점수 상위 TOP_N 개 후보만 대상으로(선정은 점수순), **선정 근거 수(확신도)에 비례**해 목표
금액을 잡아 정수 주식으로 내림 배분한 뒤(1차), 잔여 현금을 그리디로 재투입한다(2차).
2차는 확신도 대비 투입액이 가장 적은 종목부터 1주씩 추가 매수해 배분을 채운다. 단
한 종목 투입은 시드의 MAX_NAME_PCT 비율을 넘지 않도록 캡을 둬(고정금액이 아닌 시드 대비),
과집중을 막는다. 하한가에선 손절이 물리적으로 불가하므로(2026-07-10 HLB 사건: 저가주가
잔여 현금을 흡수해 시드 35% → 하한가 1방에 포트 -8%) 최악 단일 종목 손실은 이 캡으로만
봉쇄된다. 예외로 **첫 1주**는 캡을 넘어도 시드의 FIRST_SHARE_CAP_MULT×캡까지 허용한다 —
1주가 최소 매매 단위라 고가주(삼성전자 등)를 캡이 통째로 걸러내면 분산이 오히려 줄기
때문이다(캡 초과 '누적 매수'만 금지되고, 시드가 커지면 예외는 자연히 무의미해진다).

[등가중이 기본인 근거] 실거래 표본 분석 결과 종합점수는 종가베팅 익일 청산 손익을 예측하지
못했다(점수↔손익 음의 상관). 점수비례·상위집중 사이징은 '지는 고점수 종목'에 자본을
더 실어 변동성만 키웠다. 그래서 사이징에서 **점수 크기 tilt 는 여전히 쓰지 않는다**.
선정 컷(TOP_N)도 같은 이유로 **표 수 우선 → 점수 2차**다(점수는 동률 처리에만).
점수 예측력이 회복되면 재검토.

[확신도(conviction) 가중] 등가중의 단위는 '종목'이 아니라 **선정 근거 1개**다. 같은 종목이
여러 선정 근거에 동시에 걸렸으면(예: 룰 2개 매칭 + 점수 top-N 에도 포함 → 3표) 그 표 수만큼
목표금액을 키운다. 점수 '크기'가 아니라 서로 다른 근거의 **중복 매칭 개수**를 쓰므로 위
등가중 근거(점수 크기의 예측력 없음)와 충돌하지 않는다. 표 수는 호출부가 `conviction`
필드로 넣어주고(`conviction_from_signal`), 배분기는 1 ~ CONVICTION_MAX_MULT 로 클램프한다.
`conviction` 이 없으면 전부 1 = 종전 등가중과 완전히 동일하다.
⚠️ **미검증 가정**: "근거가 많을수록 기대값이 높다"는 통설이고 백테스트로 확인한 바 없다.
집행 로그(`audit_log('seed_conviction')`)로 표 수와 실현손익을 사후 채점할 수 있게 남긴다.
되돌리려면 `.env` `SEED_CONVICTION_MAX_MULT=1.0` (배분기 코드 수정 불필요).

allocate(seed, candidates):
  candidates: [{"stk_cd", "score", "price", "conviction"?} ...]  (price<=0 이면 배분 0)
  반환: 동일 리스트에 "shares", "cost" 추가 (상위 TOP_N 밖 / 무효가는 0)
"""

from core.config import SEED_MAX_NAME_PCT, SEED_CONVICTION_MAX_MULT

# 배분 대상 후보 수 상한 — 점수 상위 N개만 매수
TOP_N = 10
# 종목당 최대 투입 비율은 .env(→ core.config) 로 튜닝한다.
MAX_NAME_PCT = SEED_MAX_NAME_PCT
# 첫 1주 예외 상한 배수 — 주가가 캡×이 배수 이내인 고가주는 1주까지만 캡 초과를 허용.
# (기본 캡 25% × 2 = 시드 50%: 캡 강화 전의 단일 종목 상한과 같아 고가주 포함 범위는 유지)
FIRST_SHARE_CAP_MULT = 2.0
# 확신도 가중 상한 — 근거가 이보다 많아도 이 배수까지만 실어준다(1.0 이면 확신도 가중 off).
CONVICTION_MAX_MULT = SEED_CONVICTION_MAX_MULT


def conviction_from_signal(sig: dict, score_top_n: int | None) -> int:
    """이 시그널의 선정 근거 수(표 수). 최소 1.

    표 = 매칭된 selector rule 개수(`trade_signal.rule_names` 콤마 목록) + **legacy 점수 1표**
    (점수 top-N 에도 들었으면). 점수 선정분(rule_names 없음)은 점수 1표뿐이라 1이 된다.
    `score_top_n` 은 그날 선정 종목 수 근사값(`repository/edge_rule.get_selected_count`) —
    `edge_execution.in_scope` 의 '점수 top-N 에도 포함' 판정과 **같은 기준**을 쓴다.
    모르면(None) 점수 표를 세지 않는다(보수적 — 확신도를 부풀리지 않는다).
    """
    tags = {t.strip() for t in (sig.get("rule_names") or "").split(",") if t.strip()}
    votes = len(tags)
    rank = sig.get("rank_no")
    if score_top_n and rank is not None and int(rank) <= int(score_top_n):
        votes += 1
    return max(1, votes)


def _weight(c: dict) -> float:
    """후보의 확신도 가중치 — 없거나 이상값이면 1.0(등가중). 상한은 CONVICTION_MAX_MULT."""
    try:
        w = float(c.get("conviction") or 1)
    except (TypeError, ValueError):
        w = 1.0
    return min(max(w, 1.0), max(CONVICTION_MAX_MULT, 1.0))


def allocate(seed: int, candidates: list[dict]) -> list[dict]:
    for c in candidates:
        c.setdefault("shares", 0)
        c.setdefault("cost", 0)

    # 유효가(>0) 후보를 **표 수(확신도) 내림차순 → 점수 내림차순**으로 정렬해 상위 TOP_N 개만
    # 배분 대상으로 삼는다. 사이징이 이미 표 비례라 컷도 같은 자를 쓴다 — 표가 많은 종목을
    # 컷에서 떨어뜨리고 표가 적은 종목을 남기면 두 단계가 서로 반대로 움직인다.
    # 정렬 키는 `_weight`(클램프된 표 수)라 `CONVICTION_MAX_MULT=1.0`(확신도 off)이면
    # 전원 1.0 이 되어 **종전의 점수순 컷으로 정확히 되돌아간다**(.env 하나로 롤백 유지).
    priced = [c for c in candidates if (c.get("price") or 0) > 0]
    priced.sort(key=lambda c: (_weight(c), max(c.get("score") or 0, 0)), reverse=True)
    items = priced[:TOP_N]

    # 확신도 가중: 선정 근거 1표를 등가중 단위로 본다(표가 없으면 전원 1 = 종전 등가중).
    n = len(items)
    if seed <= 0 or n == 0:
        return candidates
    weights = [_weight(c) for c in items]
    wsum = sum(weights)

    # 종목당 최대 투입금액 — 시드 대비 비율 캡(이 금액을 넘게는 배분하지 않는다).
    # 확신도가 높아도 이 캡은 그대로다 — 하한가 1방 손실 봉쇄는 캡만이 하는 일이다.
    cap = seed * MAX_NAME_PCT

    # 1차: 표 비례 목표금액(캡 적용) → 정수 주식 내림 배분
    for c, w in zip(items, weights):
        target = min(seed * w / wsum, cap)
        c["shares"] = int(target // c["price"])
        c["cost"] = c["shares"] * c["price"]

    # 2차: 잔여 현금 그리디 재투입 — **확신도 대비** 투입액(cost/w)이 가장 적은 종목부터
    #   1주씩 추가 매수해 배분을 표 비례로 채운다(확신도가 전원 1이면 종전의 '최소 투입
    #   우선'과 동일). 한 주 더 사면 종목당 캡(cap)을 넘는 종목은 제외하며, 매수 가능
    #   종목이 없을 때까지(잔여 < 최저가 또는 전원 캡 도달) 채운다.
    #   동률이면 items 순서(=표 수 → 점수순)로 안정 정렬된다.
    #   예외: 1주가 최소 매매 단위라, 주가가 캡을 넘는 고가주도 **첫 1주**는
    #   cap×FIRST_SHARE_CAP_MULT 이내면 허용한다(누적 매수로 캡을 넘는 건 계속 금지).
    leftover = seed - sum(c["cost"] for c in items)
    first_share_cap = cap * FIRST_SHARE_CAP_MULT
    while True:
        best = None
        best_norm = float("inf")
        for c, w in zip(items, weights):
            if c["price"] <= 0 or c["price"] > leftover:
                continue
            if c["cost"] + c["price"] > cap and not (
                c["shares"] == 0 and c["price"] <= first_share_cap
            ):
                continue
            norm = c["cost"] / w
            if norm < best_norm:
                best_norm = norm
                best = c
        if best is None:
            break
        best["shares"] += 1
        best["cost"] += best["price"]
        leftover -= best["price"]

    return candidates
