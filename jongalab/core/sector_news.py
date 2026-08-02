"""미매칭 뉴스 → 섹터·거시 라벨 (프리필터 + OpenAI 벌크 판정).

## 왜 이 모듈이 있나
`news_matcher` 는 헤드라인에서 **상장 사명**을 찾아야만 뉴스를 통과시킨다. 그래서 "호남권
반도체 국가산단 후보지 지정"·"조선 2.7조 방산 1.7조 역대급 실적" 같은 **산업·정책 뉴스는
어느 종목에도 붙지 못하고 통째로 버려진다**(실측 2026-07-31 텔레그램 수집률 34%). 버려진
헤드라인은 2026-07-30부터 `content_skip(platform='news', reason='no_match')` 에 코퍼스로
쌓고 있고, 이 모듈이 거기에 섹터·방향 라벨을 붙여 검정 표본으로 만든다.

## 왜 프리필터가 먼저인가 (비용이 아니라 신호 대 잡음)
코퍼스는 하루 800건인데 실측 샘플 60건 기준 절반 이상이 연예·스포츠·사고·날씨·지역행정·
코인·해외 개별기업이다. 전건을 LLM 에 넣으면 값도 비싸지만 **응답의 대부분이 '무관'이 되어
배치당 유효 판정이 몇 건 안 남는다**. 그래서 산업·정책·거시 어휘(`_TOPIC_RE`)로 1차를 치고
LLM 은 통과분의 **섹터 확정과 방향**만 맡는다. 프리필터는 화이트리스트다 — 블랙리스트로
노이즈를 열거하면 끝이 없고, 새 잡음 유형이 들어올 때마다 조용히 뚫린다.
통과율은 워커가 로그·요약에 남긴다(너무 낮으면 어휘가 좁다는 뜻 — 감사 지표).

## 왜 섹터 어휘를 고정하나
라벨의 유일한 쓸모는 `daily_stock_report.sector` 와 조인해 익일 갭을 재는 것이다. LLM 이
"반도체"라고 답하면 유니버스 어휘("전기/전자")와 안 붙어 표본이 통째로 날아간다. 그래서
실제 유니버스 분포에서 뽑은 `SECTORS` 화이트리스트만 허용하고, 벗어나면 버린다(무관 처리).

**점수 무영향**: 라벨은 news_sector_label 에만 적재되고 score_candidate·시드 게이트는 보지
않는다. 사전검정에서 섹터 뉴스 '건수' 축은 이미 무신호(t=+0.16)라, 남은 미검증 지점인
'방향'을 재기 전까지 소비 경로를 만들지 않는다 — 상세 근거는 sql/45 주석.
"""
import logging
import re

from core.ai_service import complete_json

logger = logging.getLogger("SectorNews")

# 허용 섹터 — daily_stock_report.sector 실측 분포에서 n>=7 인 키움 업종 어휘(2026-08-03).
# 롱테일(2차전지·AMOLED_소재 등 테마성 표기)은 유니버스 행이 한 자릿수라 검정이 안 된다.
SECTORS = (
    "전기/전자", "기계/장비", "운송장비/부품", "금융", "화학", "일반서비스",
    "IT 서비스", "유통", "제약", "건설", "금속", "보험", "통신",
    "의료/정밀기기", "증권", "운송/창고",
)
SCOPES = ("섹터", "거시", "무관")

# 발행처 말머리([한국경제]·【속보】)와 본문 뒤 기사 URL 제거 — 텔레그램 헤드라인은
# "제목 https://..." 한 덩어리로 저장돼 있어 그대로 넣으면 프롬프트가 URL 로 채워진다.
_BRACKET_RE = re.compile(r"\[[^\]]*\]|【[^】]*】")
_URL_RE = re.compile(r"https?://\S+")

# 산업·정책·거시 어휘 화이트리스트(프리필터). 여기 걸리지 않으면 LLM 에 보내지 않는다.
#
# 한글 어휘는 **부분일치**로 둔다 — 조사·복합어가 붙는 게 정상이라(반도체'주', 관세'율')
# 경계를 걸면 오히려 놓친다. 대신 짧은 낱말이 엉뚱한 복합어에 박히는 함정만 개별 차단한다
# (2026-08-03 dry-run 실측: '해운'→해운대, '핵'→핵심, 'AI'→AIM인베스트).
_TOPIC_KO_RE = re.compile(
    # 산업·섹터
    r"반도체|파운드리|메모리|D램|낸드|배터리|2차전지|이차전지|양극재|음극재"
    r"|조선|선박|해운(?!대)|방산|무기|자동차|전기차|타이어|철강|제철|정유|석유화학|화학"
    r"|건설|건자재|시멘트|원전|원자력|바이오|제약|임상|신약|의료기기|백신"
    r"|통신|인공지능|데이터센터|클라우드|디스플레이|스마트폰|가전"
    r"|태양광|풍력|수소|로봇|우주|위성|드론|면세|유통|백화점|편의점"
    r"|항공|물류|은행|보험|증권|카드사|핀테크|식품|화장품|게임|엔터|콘텐츠|미디어"
    # 정책·거시
    r"|정부|정책|규제|관세|국책|예산|법안|국회|산업부|금융위|공정위|한은|한국은행"
    r"|기준금리|금리|환율|원달러|유가|수출|수입|무역|경상수지|물가|인플레|고용지표"
    r"|코스피|코스닥|증시|뉴욕증시|나스닥|선물시장|외국인 순매|기관 순매"
    # 지정학 — '핵'은 '핵심'에 박히므로 결합형만 받는다
    r"|전쟁|휴전|정전협정|종전|공습|미사일|핵무기|핵실험|비핵화|핵협상|핵합의"
    r"|제재|봉쇄|호르무즈|중동|이란|이스라엘|하마스|러시아|우크라|북한|대만"
    r"|남중국해|무역분쟁|트럼프|시진핑"
)
# ASCII 약어는 **토큰 경계**를 요구한다 — 경계 없이 두면 AI 가 AIM·CHAIN 안에서 잡힌다.
_TOPIC_EN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:AI|5G|6G|CPI|PPI|GDP|FOMC|OLED|LCD|EV|IPO|M&A)(?![A-Za-z0-9])"
)


def clean_headline(raw: str) -> str:
    """발행처 말머리·URL 을 걷어낸 판정용 헤드라인 (255자 컬럼에 맞춰 자름)."""
    text = _URL_RE.sub(" ", _BRACKET_RE.sub(" ", raw or ""))
    return " ".join(text.split())[:255]


def is_topical(headline: str) -> bool:
    """산업·정책·거시 어휘가 있는가 (LLM 판정 대상 여부)."""
    text = headline or ""
    return bool(_TOPIC_KO_RE.search(text) or _TOPIC_EN_RE.search(text))


SECTOR_NEWS_PROMPT = """당신은 한국 주식 산업 분석가다. 아래는 개별 상장사 이름이 잡히지 않은 뉴스 헤드라인 목록이다.
각 헤드라인이 **한국 증시의 어느 업종에 영향을 주는 내용인지**와 그 **방향**을 판정하라.
헤드라인에 명시된 내용만 근거로 하고 없는 사실을 지어내지 마라.

[판정 기준]
- scope: 특정 업종에 영향이 국한되면 "섹터", 증시 전체·거시(금리·환율·지수·지정학·무역정책)면 "거시",
  증시와 무관하거나(연예·스포츠·사고·날씨·지역행정) 영향 업종을 특정할 수 없으면 "무관".
- sector: scope 가 "섹터"일 때만, 아래 목록에서 **정확히 하나** 고른다(목록 밖 표현 금지).
  {sectors}
  해외 기업 뉴스라도 **국내 상장사에 직접 파급되는 공급망·업황 내용이면** 해당 업종을 고르고,
  단순 해외 기업 동향이면 "무관"으로 두라.
- ⚠️ **업종을 억지로 채우지 마라.** "그 업종과 말이 된다" 수준이면 부족하고, **국내 상장사의
  업황·수주·규제에 실제로 파급되는 내용**일 때만 섹터로 판정한다. 판단이 서지 않으면 "무관"이 정답이다.
  무관 예: 지역 행정·지자체 사업, 대학·중소 비상장기업 소식, 개별 사건사고, 해외 기업의 단순 동향.
- sentiment: 해당 업종(거시면 한국 증시 전체)에 대한 **방향**. 0~100 정수. 척도:
  85=매우 강한 호재(대형 정책 집행·업황 급반등) / 70=호재 / 55=약한 호재
  / 50=방향 판별 불가 / 45=약한 악재 / 30=악재 / 15=매우 강한 악재(규제 충격·수요 급랭)
  ⚠️ **50 은 방향을 정말 못 읽을 때만 쓰는 값이다.** 실제 뉴스는 대부분 어느 쪽으로든 기울어 있다 —
  "증시 급반등"·"투자 확대"·"수주 증가"는 호재이고, "규제 강화"·"수요 위축"·"공급 차질"은 악재다.
  개별 종목의 주가를 전망하라는 것이 아니라, **그 업종에 유리한 소식인가 불리한 소식인가**를 답하라.
  전부 50 으로 답하는 것은 오답으로 간주한다.
- reason: 판정 근거 한 문장. 헤드라인의 어느 대목을 봤는지 밝혀라.

[헤드라인]
{blocks}

아래 JSON 형식으로만 답하라. items 에는 위 헤드라인 전부를 idx 그대로 포함하라.
{{
  "items": [
    {{
      "idx": <헤드라인 번호>,
      "scope": "<섹터 | 거시 | 무관>",
      "sector": "<업종 목록 중 하나 | null>",
      "sentiment": <0~100 정수>,
      "reason": "<판정 근거 한 문장>"
    }}
  ]
}}"""


def build_prompt(items: list[dict]) -> str:
    """items: [{"idx": int, "headline": str}, ...] → 프롬프트 문자열."""
    blocks = "\n".join(f"{it['idx']}. {it['headline']}" for it in items)
    return SECTOR_NEWS_PROMPT.format(
        sectors=" | ".join(SECTORS), blocks=blocks,
    )


def _clean(item: dict) -> dict | None:
    """LLM 항목 1개를 화이트리스트·범위로 정규화. idx 가 없으면 None(버림).

    섹터가 화이트리스트 밖이면 **무관으로 강등**한다 — 유니버스 어휘와 조인되지 않는 라벨은
    검정에 쓸 수 없는데 '섹터'로 남겨두면 집계 분모만 부풀린다.
    """
    idx = item.get("idx")
    if isinstance(idx, bool) or not isinstance(idx, int):
        return None

    scope = str(item.get("scope") or "").strip()
    if scope not in SCOPES:
        scope = "무관"

    sector = str(item.get("sector") or "").strip()
    if scope != "섹터" or sector not in SECTORS:
        if scope == "섹터":
            logger.debug("허용 밖 섹터 '%s' — 무관으로 강등", sector)
            scope = "무관"
        sector = None

    sentiment = item.get("sentiment")
    if isinstance(sentiment, bool) or not isinstance(sentiment, int) or not (0 <= sentiment <= 100):
        sentiment = None

    return {
        "idx": idx,
        "scope": scope,
        "sector": sector,
        "sentiment": sentiment,
        "reason": (str(item.get("reason") or "").strip()[:255] or None),
    }


def parse_response(data: dict | None, expected: set[int] | None = None) -> dict[int, dict]:
    """LLM 응답 → {idx: labels}. 형식 불량은 조용히 버린다(빈 dict = 라벨 없음 = 미개입).

    expected 를 주면 요청하지 않은 idx(환각)를 걸러낸다 — 벌크 판정은 헤드라인을 번호로만
    구분하므로 없는 번호가 섞이면 엉뚱한 기사에 라벨이 붙는다.
    """
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        labels = _clean(item)
        if not labels:
            continue
        if expected is not None and labels["idx"] not in expected:
            logger.warning("요청에 없는 idx 응답 무시: %s", labels["idx"])
            continue
        out[labels["idx"]] = labels
    return out


def judge_batch(items: list[dict]) -> dict[int, dict]:
    """헤드라인 묶음 1회 판정. items: [{"idx","headline"}, ...].

    반환: {idx: labels} (실패·형식 불량은 빈 dict — 호출부는 저장을 건너뛰고 다음 실행에 재시도).
    """
    if not items:
        return {}
    try:
        data = complete_json(build_prompt(items), temperature=0)
    except Exception as e:
        logger.warning("섹터 뉴스 판정 실패(%d건): %s", len(items), e)
        return {}
    return parse_response(data, expected={it["idx"] for it in items})


def judge_headlines(items: list[dict], batch_size: int) -> dict[int, dict]:
    """전건을 배치로 나눠 판정 — 한 배치 실패가 나머지를 막지 않는다.

    배치를 나누는 이유는 비용이 아니라 **JSON 응답 신뢰도**다(항목이 많으면 누락이 늘고
    한 번의 파싱 실패로 전건을 잃는다). news_material_judge.judge_materials 와 같은 규약.
    """
    out: dict[int, dict] = {}
    size = max(1, batch_size)
    for i in range(0, len(items), size):
        out.update(judge_batch(items[i:i + size]))
    return out
