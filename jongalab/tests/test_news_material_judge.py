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


# ── derive_durability: 사실 축 → 등급 (규칙 v2, 2026-08-05) ──
# v2 의 뜻: '연속'은 다음 사건이 남았고 **임박**했거나 산업사이클인 재료다.
# amount_locked 는 실측 무차별이라 합성에서 빠졌고(수집은 유지), 시점 축이 그 자리를 대신한다.

def test_마무리_국면은_소진이다():
    labels = {"next_milestone": 1, "milestone_horizon": "1주내", "stage": "마무리",
              "driver_scope": "산업사이클"}
    # 다음 사건이 임박했다고 해도 마무리 국면이면 소진이 이긴다(순서가 우선순위)
    assert derive_durability(labels) == "소진"


def test_다음사건이_한달_안이면_연속이다():
    for horizon in ("1주내", "1개월내"):
        labels = {"next_milestone": 1, "milestone_horizon": horizon, "stage": "첫발표",
                  "driver_scope": "종목단독"}
        assert derive_durability(labels) == "연속"


def test_다음사건이_멀면_연속이_아니라_중립이다():
    """하루만 들고 있는 전략에서 '내년 어느 날'은 익일 매수세를 만들지 않는다 — v1 의 핵심 결함."""
    labels = {"next_milestone": 1, "milestone_horizon": "그이후", "stage": "첫발표",
              "driver_scope": "종목단독"}
    assert derive_durability(labels) == "중립"
    assert derive_durability({**labels, "milestone_horizon": "불명"}) == "중립"


def test_시점이_멀어도_산업사이클이면_연속이다():
    labels = {"next_milestone": 1, "milestone_horizon": "그이후", "stage": "진행",
              "driver_scope": "산업사이클"}
    assert derive_durability(labels) == "연속"


def test_다음사건이_없으면_수치확정과_무관하게_소진이다():
    """v1 은 amount_locked=1 을 함께 요구해 단발 재료 일부가 '중립'으로 새어나갔다."""
    for locked in (0, 1, None):
        labels = {"next_milestone": 0, "amount_locked": locked, "stage": "첫발표",
                  "driver_scope": "종목단독"}
        assert derive_durability(labels) == "소진"


def test_재료_특정_실패는_소진으로_단정하지_않는다():
    """'소진'은 부정 진술이라 재료가 특정돼야 성립한다 — 아니면 '모르겠다'가 '없다'로 바뀐다.
    이 가드가 없으면 실측 프로브에서 판정 6건 중 5건이 전부 소진으로 몰렸다."""
    base = {"next_milestone": 0, "driver_scope": "불명"}
    assert derive_durability({**base, "stage": "불명"}) is None
    assert derive_durability({**base, "stage": None}) is None
    assert derive_durability({**base, "stage": "진행"}) == "소진"
    # '연속'은 긍정 진술이라 stage 불명이어도 성립한다(비대칭이 의도한 설계다)
    assert derive_durability({"next_milestone": 1, "milestone_horizon": "1주내",
                              "stage": "불명"}) == "연속"


def test_필수축_결측은_None이고_중립으로_눕지_않는다():
    base = {"next_milestone": 1, "milestone_horizon": "1주내", "stage": "첫발표"}
    assert derive_durability({**base, "next_milestone": None}) is None
    # amount_locked 는 더 이상 필수 축이 아니다(실측 무차별 → 합성 제외)
    assert derive_durability({**base, "amount_locked": None}) == "연속"


def test_stage_불명은_판정을_막지_않는다():
    """v1 은 stage 불명이면 전부 None 이라 커버리지를 깎았다. 실측에서 이 집단은 나쁘지 않았다."""
    base = {"next_milestone": 1, "milestone_horizon": "1주내", "driver_scope": "종목단독"}
    assert derive_durability({**base, "stage": "불명"}) == "연속"
    assert derive_durability({**base, "stage": None}) == "연속"


def test_합성_버전은_라벨이_있을_때만_붙는다():
    """v1/v2 표본을 분리하는 근거 — 라벨 없는 행에 버전만 남으면 표본 구분이 깨진다."""
    from core.news_material_judge import DURABILITY_VERSION
    ok = parse_response({"items": [_ITEM]})["005930"]
    assert ok["durability_v"] == DURABILITY_VERSION
    none = parse_response({"items": [{**_ITEM, "next_milestone": None}]})["005930"]
    assert none["durability"] is None and none["durability_v"] is None


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
    "next_milestone": 1, "milestone_horizon": "1주내", "amount_locked": 0,
    "material_size_eok": 1200, "driver_scope": "산업사이클",
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
    # stage 불명은 더 이상 판정을 막지 않는다(v2) — milestone 축으로 판정된다
    assert labels["durability"] == "연속"


def test_플래그는_0_1_만_받고_그_밖은_미판정이다():
    labels = parse_response({"items": [{**_ITEM, "next_milestone": "예", "amount_locked": 2}]})
    assert labels["005930"]["next_milestone"] is None
    assert labels["005930"]["amount_locked"] is None
    assert labels["005930"]["durability"] is None


def test_시점_화이트리스트와_금액_범위를_정규화한다():
    """금액은 자릿수 착오가 잦다 — 비현실적 값은 버려야 시총 대비 비율이 오염되지 않는다."""
    labels = parse_response({"items": [{**_ITEM, "milestone_horizon": "내일쯤",
                                        "material_size_eok": "1200억"}]})["005930"]
    assert labels["milestone_horizon"] == "불명"
    assert labels["material_size_eok"] is None
    over = parse_response({"items": [{**_ITEM, "material_size_eok": 10 ** 9}]})["005930"]
    assert over["material_size_eok"] is None
    neg = parse_response({"items": [{**_ITEM, "material_size_eok": -5}]})["005930"]
    assert neg["material_size_eok"] is None


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


def test_시세보도는_판정_코퍼스에서_빠진다():
    """네이버 소스 유입으로 "급락·약세" 기사가 대량 섞이는데, 그게 sentiment 를 끌어내리면
    veto_bad_news(live)가 '재료 악재'가 아니라 '어제 빠졌다'로 발동한다 — 그 경로 차단."""
    items = [
        {"d": "2026-08-05", "headline": "A사, FDA 실사 종결"},
        {"d": "2026-08-05", "headline": "A사 5% 급락[특징주]"},
        {"d": "2026-08-05", "headline": "코스닥 약세에 A사 하락 마감"},
    ]
    picked = select_headlines(items, limit=20, lookback_days=5)
    assert [it["headline"] for it in picked] == ["A사, FDA 실사 종결"]
    # 시세보도만 있으면 블록이 비고 → 그 종목은 라벨 없음(NULL = rule 미개입)
    assert select_headlines(items[1:], limit=20, lookback_days=5) == []


def test_리드문_발췌가_블록에_붙는다():
    """시점·금액 축은 제목에 거의 안 실려서 이 발췌가 유일한 근거다."""
    block = build_block("A사", "000001", [
        {"d": "2026-08-05", "headline": "A사, 대규모 수주",
         "body_preview": "A사는 5일 1,200억 원 규모 계약을 체결했다고 밝혔다."},
        {"d": "2026-08-05", "headline": "발췌 없는 기사"},
    ])
    assert "1,200억" in block
    assert "발췌 없는 기사" in block   # 발췌가 없어도 제목은 들어간다
