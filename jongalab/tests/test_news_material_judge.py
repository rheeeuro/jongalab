"""뉴스 재료 지속성 판정의 순수 로직 계약 고정 (DB·네트워크 무의존).

라벨이 자금 경로에 직접 닿지는 않지만(점수 무영향), 여기가 틀리면 **엣지 검증 표본 전체가
조용히 오염된다** — 잘못된 라벨은 결과가 나올 때까지 티가 안 난다. 특히:
  · 결측을 '중립'으로 눕히지 않는지(derive_durability → None)
  · 시세보도를 후속 재료로 세지 않는지(count_followup_days)
  · 요청하지 않은 ticker(환각)를 다른 종목에 붙이지 않는지(parse_response)
"""
from core.news_material_judge import (
    build_block,
    count_followup_days,
    derive_durability,
    is_price_report,
    parse_response,
    select_headlines,
)


# ── derive_durability: 4축 → 등급 ──

def test_마무리_국면은_소진이다():
    labels = {"next_milestone": 1, "amount_locked": 0, "stage": "마무리",
              "driver_scope": "산업사이클"}
    # 다음 사건이 남았다고 해도 마무리 국면이면 소진이 이긴다(순서가 우선순위)
    assert derive_durability(labels) == "소진"


def test_다음사건_남고_수치_미확정은_연속이다():
    labels = {"next_milestone": 1, "amount_locked": 0, "stage": "첫발표",
              "driver_scope": "종목단독"}
    assert derive_durability(labels) == "연속"


def test_수치_확정이어도_산업사이클이면_연속이다():
    labels = {"next_milestone": 1, "amount_locked": 1, "stage": "진행",
              "driver_scope": "산업사이클"}
    assert derive_durability(labels) == "연속"


def test_수치_확정에_다음사건_없으면_소진이다():
    labels = {"next_milestone": 0, "amount_locked": 1, "stage": "첫발표",
              "driver_scope": "종목단독"}
    assert derive_durability(labels) == "소진"


def test_애매한_조합은_중립이다():
    labels = {"next_milestone": 0, "amount_locked": 0, "stage": "진행",
              "driver_scope": "종목단독"}
    assert derive_durability(labels) == "중립"


def test_필수축_결측은_None이고_중립으로_눕지_않는다():
    base = {"next_milestone": 1, "amount_locked": 0, "stage": "첫발표"}
    assert derive_durability({**base, "next_milestone": None}) is None
    assert derive_durability({**base, "amount_locked": None}) is None
    assert derive_durability({**base, "stage": "불명"}) is None
    assert derive_durability({**base, "stage": None}) is None


# ── 시세보도 판별 / 후속 재료 채점 ──

def test_시세보도_헤드라인_판별():
    assert is_price_report("[이데일리] 한화오션, 4% 가까이↑…트럼프 발언[특징주]")
    assert is_price_report("美 반도체주 강세에 프리마켓서 삼성전자 5%↑")
    # 재료 기사는 시세보도가 아니다 — 평범한 '상승/하락'을 어휘에 넣지 않은 이유
    assert not is_price_report('HLB "간암 신약 허가 걸림돌 해소" FDA 실사 VAI 종결')
    assert not is_price_report("현대차, 인도 공장 수출 물량 상승 전망")


def test_후속재료는_시세보도_제외한_날짜수를_센다():
    rows = [
        {"d": "2026-07-20", "headline": "A사, FDA 실사 종결"},
        {"d": "2026-07-20", "headline": "A사 2%↑ 급등[특징주]"},   # 같은 날 + 시세보도
        {"d": "2026-07-21", "headline": "A사 상한가"},              # 시세보도만 → 세지 않음
        {"d": "2026-07-22", "headline": "A사, 본계약 체결"},
    ]
    assert count_followup_days(rows) == 2  # 07-20, 07-22
    assert count_followup_days([]) == 0


# ── 응답 파싱 ──

_ITEM = {
    "ticker": "005930", "sentiment_score": 70, "catalyst_type": "수주계약",
    "next_milestone": 1, "amount_locked": 0, "driver_scope": "산업사이클",
    "stage": "첫발표", "summary": "요약", "reason": "근거",
}


def test_정상_응답은_등급까지_합성된다():
    out = parse_response({"items": [_ITEM]})
    assert out["005930"]["durability"] == "연속"
    assert out["005930"]["sentiment"] == 70
    assert out["005930"]["catalyst"] == "수주계약"


def test_화이트리스트_밖_값은_안전한_기본값으로_정규화된다():
    item = {**_ITEM, "catalyst_type": "우주개발", "driver_scope": "글로벌",
            "stage": "협의중", "sentiment_score": 120}
    labels = parse_response({"items": [item]})["005930"]
    assert labels["catalyst"] == "기타"
    assert labels["driver_scope"] == "불명"
    assert labels["stage"] == "불명"
    assert labels["sentiment"] is None
    assert labels["durability"] is None  # stage 불명 → 미판정


def test_플래그는_0_1_만_받고_그_밖은_미판정이다():
    labels = parse_response({"items": [{**_ITEM, "next_milestone": "예", "amount_locked": 2}]})
    assert labels["005930"]["next_milestone"] is None
    assert labels["005930"]["amount_locked"] is None
    assert labels["005930"]["durability"] is None


def test_요청하지_않은_ticker_는_버린다():
    out = parse_response({"items": [_ITEM, {**_ITEM, "ticker": "999999"}]},
                         expected={"005930"})
    assert set(out) == {"005930"}


def test_형식_불량_응답은_빈_dict():
    assert parse_response(None) == {}
    assert parse_response({"items": "nope"}) == {}
    assert parse_response({"items": [{"sentiment_score": 50}]}) == {}  # ticker 없음


# ── 프롬프트 블록 ──

def test_블록은_최신_헤드라인을_남기고_잘린다():
    items = [{"d": f"2026-07-{d:02d}", "headline": f"기사{d}"} for d in range(1, 31)]
    block = build_block("삼성전자", "005930", items)
    assert "005930" in block
    assert "기사30" in block          # 최신은 남는다(stage 판정 근거)
    assert "기사01" not in block      # 오래된 쪽이 잘린다
    assert block.count("\n- ") <= 20


def test_뉴스가_몰려도_과거_날짜가_블록에_남는다():
    """당일만 20건으로 채우면 stage(첫 발표/후속) 판정 근거가 사라진다 — 룩백의 존재 이유."""
    items = []
    for day in ("2026-07-25", "2026-07-28", "2026-07-29"):
        n = 3 if day != "2026-07-29" else 40   # 당일에 뉴스 폭증
        items += [{"d": day, "headline": f"{day} 기사{i}"} for i in range(n)]
    picked = select_headlines(items, limit=20, lookback_days=5)
    assert len(picked) == 20
    days = {it["d"] for it in picked}
    assert days == {"2026-07-25", "2026-07-28", "2026-07-29"}


def test_채널_복제_동일본문은_한_건만_남는다():
    items = [
        {"d": "2026-07-29", "headline": "A사 수주 계약"},
        {"d": "2026-07-29", "headline": "A사  수주   계약"},   # 공백만 다름
        {"d": "2026-07-29", "headline": "A사 실적 발표"},
    ]
    assert len(select_headlines(items, limit=20, lookback_days=5)) == 2


def test_빈_헤드라인은_블록에서_제외된다():
    block = build_block("A사", "000001", [{"d": "2026-07-20", "headline": "  "},
                                          {"d": "2026-07-20", "headline": "실제 기사"}])
    assert block.count("\n- ") == 1
