"""뉴스 '재료 지속성' 벌크 판정 (OpenAI, ai_service.complete_json 경유).

## 왜 이 모듈이 있나
종가베팅은 종가 매수 → 익일 개장 청산이라, 다음 날 아침 살 사람이 있어야 한다. 가설은
**"수치가 이미 확정된 단발 이벤트는 종가에 소진되고, 다음 마일스톤이 남은 연속 재료는
익일까지 이어진다"** 이다. 실측 단서(2026-07-01~27, next_open_ret 기준, n 이 작아 근거는 아님):

| 재료 유형 | n | 익일 시가 | 익일 종가 | 장중 |
|---|---|---|---|---|
| 정책테마 | 5 | +3.68% | +3.82% | **+0.15%p** |
| 임상승인 | 4 | +2.47% | +5.59% | **+3.12%p** |
| 실적     | 7 | -2.03% | -4.19% | -2.16%p |
| 수주계약 | 3 | -1.77% | -5.08% | -3.31%p |
| (유니버스) | 588 | -0.08% | -1.74% | -1.66%p |

다음 마일스톤이 남은 재료(정책 집행 일정·다음 임상 단계)만 장중에 죽지 않았고, 수치가
확정된 단발 이벤트는 유니버스 평균보다 더 빨리 페이드했다 → 가설과 정합. 그래서 **측정한다.**

## 왜 LLM 이어야 하나 (news_matcher·집계 라벨과의 차이)
'언급의 지속'은 `news_mention` 카운트로 공짜로 계산되고, 실제로 재보니 시총 프록시였다
(대형주는 매일 아침 기사가 난다). **재료 자체의 지속성은 DB 에 프록시가 없다** — 헤드라인
텍스트를 읽어야만 나오는 속성이라 LLM 라벨이 값싼 대안 대비 처음으로 정당화되는 축이다.

## 왜 '지속성 점수' 하나를 묻지 않나
"지속될 것 같다"는 감(感)이면 오탐 감사가 불가능하다(veto-verify-before-live 규율을 적용할
대상이 없다). 그래서 **관측 가능한 사실 4축**으로 쪼개 묻고, 지속성 등급은 코드가 결정론적으로
합성한다(`derive_durability`) — 판정 근거가 어디서 틀렸는지 육안 감사가 되고, 합성 규칙을
바꿔도 과거 라벨을 재해석할 수 있다.
  next_milestone — 재료에 다음 예정 사건이 남았나 (허가 결정·본계약·예산 집행·다음 임상 단계)
  amount_locked  — 수치가 이미 확정·소진됐나 (계약금 확정 = 1회성 / 잔고·파이프라인 = 연속)
  driver_scope   — 종목 단독인가 산업·정책 사이클인가 (사이클이면 익일 후속·동종주 확산이 붙음)
  stage          — 재료 사이클의 첫 발표 / 진행 / 마무리 (마무리 = 소진)

## 판정 근거는 '5일치' 헤드라인이다
당일 헤드라인만으로는 `stage`(첫 발표인지 세 번째 후속인지)를 알 수 없다. 종목별로 최근
NEWS_JUDGE_LOOKBACK_DAYS 일치 헤드라인을 날짜와 함께 묶어 넣는다(news_mention 14일 보존).
**한계**: 저장된 건 헤드라인 500자 + 링크 프리뷰뿐이고 본문이 없다 → 마일스톤 '날짜'까지는
판정 불가하므로 '존재 여부'만 묻는다.

돈이 걸린 판정이 아니라 연구 라벨이지만, 하루 16종목 전건 판정에는 처리량이 필요해
로컬 Ollama(건당 100~300초, 하루 5행 상한이 이 병목이었다) 대신 OpenAI 를 쓴다.
**이 모듈이 예전 `core/news_summary.py`(Ollama 단건 요약)를 대체한다** — 같은 컬럼
(news_summary/news_sentiment/news_catalyst)을 채우므로 두 경로를 남기면 어느 쪽이 라벨을
만들었는지 알 수 없어 그 파일은 삭제했다.
프롬프트는 가드 파일(core/prompts.py)이 아니라 여기 둔다(news_veto_judge 선례).

**점수 무영향**: 라벨은 daily_stock_report 에만 적재되고 score_candidate 는 보지 않는다.
'지속성=호재'는 통설이므로 rule 은 candidate 로만 등록해 발견/확인창 규율로 판정한다.
"""
import logging
import re

from core.ai_service import complete_json
from core.config import (
    NEWS_JUDGE_BATCH_SIZE,
    NEWS_JUDGE_LOOKBACK_DAYS,
    NEWS_JUDGE_MAX_HEADLINES,
)

logger = logging.getLogger("NewsMaterialJudge")

# 재료 유형 화이트리스트 — sql/4 이래 news_catalyst 에 쓰던 집합을 그대로 유지한다
# (daily_stock_report.news_catalyst VARCHAR(20) 를 공유하므로 과거 라벨과 비교 가능해야 한다).
CATALYST_TYPES = ("실적", "수주계약", "임상승인", "M&A", "정책테마", "증자감자", "지분변동", "기타")
DRIVER_SCOPES = ("종목단독", "산업사이클", "불명")
STAGES = ("첫발표", "진행", "마무리", "불명")
DURABILITY_LEVELS = ("연속", "중립", "소진")

# 시세보도 헤드라인 판별 — '재료'가 아니라 그날 가격 움직임을 옮긴 기사다.
# 후속 재료 실현 채점(count_followup_days)에서 제외해야 한다: 갭상승이 "XX 급등" 기사를 만드는
# 역인과라, 이걸 후속 재료로 세면 "재료가 이어졌다"가 "어제 올랐다"의 동어반복이 된다
# (실측 2026-07-14~27 익일 아침 헤드라인 449건 중 95건 = 21% 가 이 부류).
# 평범한 '상승/하락'은 넣지 않는다 — "수출 상승" 같은 재료 기사까지 배제된다.
_PRICE_REPORT_RE = re.compile(
    r"급등|급락|상한가|하한가|강세|약세|치솟|폭등|폭락|↑|↓|신고가|신저가|장중|특징주|시황"
)

NEWS_MATERIAL_PROMPT = """당신은 한국 주식 재료 분석가다. 아래는 여러 종목의 최근 뉴스 속보 헤드라인이다(종목별, 날짜 오름차순).
각 종목의 '재료'가 무엇인지 파악하고, 그 재료가 **한 번의 이벤트로 끝나는 성질인지 연속적으로 이어지는 성질인지**를 판정하라.
헤드라인에 명시된 내용만 근거로 하고 추측·확대해석은 금지한다. 주가 전망을 하지 말고, 재료의 성질만 판정하라.

[판정 기준]
- next_milestone: 이 재료에 **아직 남은 다음 예정 사건**이 있으면 1, 없으면 0.
  1 예: FDA 실사 종결(→ 허가 결정 남음), MOU·수주 협의(→ 본계약 남음), 정책 발표(→ 예산 집행·후속 법안), 임상 1상 성공(→ 2상), 증설 착공(→ 가동)
  0 예: 계약 체결 완료, 실적 발표 완료, 지분 매각 완료, 이미 종결된 소송 판결
- amount_locked: 재료의 수치·규모가 **이미 확정되어 더 늘 여지가 없으면** 1, 누적·확대 여지가 있으면 0.
  1 예: "1,200억 수주 계약 체결", "2분기 영업이익 3,000억 확정", 유상증자 발행가액 확정
  0 예: 수주잔고 누적 중, 파이프라인 진행 중, 정책 예산 규모 미정, 증설 램프업 진행
- driver_scope: 재료의 동인이 그 회사만의 사건이면 "종목단독", 산업·정책 사이클(동종업계가 함께 움직이는 성질)이면 "산업사이클", 불분명하면 "불명"
- stage: 이 재료가 헤드라인에 처음 등장했으면 "첫발표", 후속 보도·진행 경과면 "진행", 마무리·종결 국면이면 "마무리", 불분명하면 "불명"
- sentiment_score: 재료 방향 0~100 정수 (호재>50, 악재<50, 중립=50)
- catalyst_type: 실적 | 수주계약 | 임상승인 | M&A | 정책테마 | 증자감자 | 지분변동 | 기타 중 하나
- 이 종목이 뉴스의 **직접 당사자가 아니거나**(시황·경쟁사 기사에 곁다리로 언급) 재료를 특정할 수 없으면
  next_milestone·amount_locked 를 null 로, stage·driver_scope 를 "불명"으로 두라. 억지로 채우지 마라.

[종목별 헤드라인]
{blocks}

아래 JSON 형식으로만 답하라. items 에는 위 종목 전부를 ticker 그대로 포함하라.
{{
  "items": [
    {{
      "ticker": "<종목코드 6자리>",
      "sentiment_score": <0~100 정수>,
      "catalyst_type": "<재료 유형>",
      "next_milestone": <1 | 0 | null>,
      "amount_locked": <1 | 0 | null>,
      "driver_scope": "<종목단독 | 산업사이클 | 불명>",
      "stage": "<첫발표 | 진행 | 마무리 | 불명>",
      "summary": "<재료 핵심 2~3줄 한글 요약. 마크다운 불필요>",
      "reason": "<지속성 판정 근거 한 문장(육안 감사용). 근거 헤드라인을 인용하라>"
    }}
  ]
}}"""


def is_price_report(headline: str) -> bool:
    """헤드라인이 '재료'가 아니라 그날 시세를 옮긴 기사인가."""
    return bool(_PRICE_REPORT_RE.search(headline or ""))


def select_headlines(items: list[dict], limit: int, lookback_days: int) -> list[dict]:
    """헤드라인 상한 안에서 **날짜를 분산**해 고른다 (입력은 created_at 오름차순).

    단순히 '최신 N건'으로 자르면 뉴스가 몰린 대형주는 20건이 전부 당일 기사가 되어
    `stage`(첫 발표인가 세 번째 후속인가) 판정 근거가 사라진다 — 룩백을 넣은 이유 자체가
    없어진다(SK하이닉스 실측: 당일만 64건). 그래서 날짜별로 먼저 배분하고, 남은 예산을
    최신 쪽에서 채운다. 같은 본문(공백 정규화)은 채널 복제라 한 건만 남긴다.
    """
    seen: set[str] = set()
    rows: list[dict] = []
    for it in items:
        headline = (it.get("headline") or "").strip()
        if not headline:
            continue
        key = " ".join(headline.split())
        if key in seen:
            continue
        seen.add(key)
        rows.append(it)
    if len(rows) <= limit:
        return rows

    by_day: dict = {}
    for it in rows:
        by_day.setdefault(it.get("d"), []).append(it)

    per_day = max(1, limit // max(1, min(lookback_days, len(by_day))))
    picked_ids: set[int] = set()
    for day in sorted(by_day):
        for it in by_day[day][-per_day:]:      # 그 날짜의 최신 per_day 건
            picked_ids.add(id(it))
    # 예산 초과분은 오래된 날짜부터 덜어내고(최신 우선), 남으면 최신 쪽에서 더 채운다.
    picked = [it for it in rows if id(it) in picked_ids][-limit:]
    if len(picked) < limit:
        chosen = {id(it) for it in picked}
        for it in reversed(rows):
            if len(picked) >= limit:
                break
            if id(it) not in chosen:
                picked.append(it)
                chosen.add(id(it))
        picked.sort(key=lambda it: rows.index(it))
    return picked


def build_block(name: str, ticker: str, items: list[dict]) -> str:
    """종목 1개의 프롬프트 블록 — 날짜 오름차순 헤드라인 묶음(날짜 분산 선별)."""
    rows = select_headlines(items, NEWS_JUDGE_MAX_HEADLINES, NEWS_JUDGE_LOOKBACK_DAYS)
    lines = [f"- ({it.get('d')}) {it['headline'].strip()}" for it in rows]
    return f"## {name}({ticker})\n" + "\n".join(lines)


def derive_durability(labels: dict) -> str | None:
    """4개 사실 축 → 지속성 등급('연속'/'중립'/'소진'). 판정 불가면 None.

    **순서가 곧 우선순위다**(disclosure_events._RULES 와 같은 규약):
      1. stage='마무리'                      → 소진 (마무리 국면은 남은 게 없다)
      2. next_milestone=1 & amount_locked=0  → 연속 (다음 사건이 남고 수치도 안 잠겼다)
      3. next_milestone=1 & 산업사이클        → 연속 (금액이 잠겨도 사이클 재료는 후속이 붙는다)
      4. next_milestone=0 & amount_locked=1  → 소진 (수치 확정 + 다음 사건 없음 = 단발)
      5. 그 외                                → 중립

    필수 축(next_milestone·amount_locked·stage) 중 하나라도 결측이면 **None** 을 반환한다 —
    라벨을 억지로 만들면 rule 이 결측을 '중립'으로 오인해 표본이 오염된다(predicate 는
    NULL 을 매칭 실패로 처리하므로 None 이 안전한 기본값).
    """
    milestone = labels.get("next_milestone")
    locked = labels.get("amount_locked")
    stage = labels.get("stage")
    if milestone is None or locked is None or not stage or stage == "불명":
        return None
    if stage == "마무리":
        return "소진"
    if milestone == 1 and locked == 0:
        return "연속"
    if milestone == 1 and labels.get("driver_scope") == "산업사이클":
        return "연속"
    if milestone == 0 and locked == 1:
        return "소진"
    return "중립"


def count_followup_days(rows: list[dict]) -> int:
    """후속 재료 실현 일수 — 시세보도를 제외한 언급이 있던 **서로 다른 날짜 수**.

    rows 항목: {"d": date|str, "headline": str} (창 필터는 호출부가 한다).
    이진(있음/없음)이 아니라 일수를 세는 이유: 10일 창이면 대형주는 거의 100% 가 '있음'이라
    이진 라벨이 시총 더미가 된다. 일수는 등급이 있어 그룹 간 비교가 된다.
    """
    return len({r["d"] for r in rows if not is_price_report(r.get("headline") or "")})


def _clean(item: dict) -> dict | None:
    """LLM 항목 1개를 화이트리스트·범위로 정규화. ticker 없으면 None(버림)."""
    ticker = str(item.get("ticker") or "").strip()
    if not ticker:
        return None

    sentiment = item.get("sentiment_score")
    if not isinstance(sentiment, int) or isinstance(sentiment, bool) or not (0 <= sentiment <= 100):
        sentiment = None

    catalyst = str(item.get("catalyst_type") or "").strip()
    if catalyst and catalyst not in CATALYST_TYPES:
        catalyst = "기타"

    def _flag(key):
        v = item.get(key)
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int) and v in (0, 1):
            return v
        return None  # null·문자열·범위 밖 = 미판정

    scope = str(item.get("driver_scope") or "").strip()
    if scope not in DRIVER_SCOPES:
        scope = "불명"
    stage = str(item.get("stage") or "").strip()
    if stage not in STAGES:
        stage = "불명"

    labels = {
        "ticker": ticker,
        "sentiment": sentiment,
        "catalyst": catalyst or None,
        "next_milestone": _flag("next_milestone"),
        "amount_locked": _flag("amount_locked"),
        "driver_scope": scope,
        "stage": stage,
        "summary": (str(item.get("summary") or "").strip() or None),
        "reason": (str(item.get("reason") or "").strip()[:255] or None),
    }
    labels["durability"] = derive_durability(labels)
    return labels


def parse_response(data: dict | None, expected: set[str] | None = None) -> dict[str, dict]:
    """LLM 응답 → {ticker: labels}. 형식 불량은 조용히 버린다(빈 dict = 라벨 없음 = 미개입).

    expected 를 주면 요청하지 않은 ticker(환각)를 걸러낸다 — 벌크 판정은 종목을 섞어 넣으므로
    존재하지 않는 코드가 섞이면 엉뚱한 종목에 라벨이 붙는다.
    """
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        labels = _clean(item)
        if not labels:
            continue
        if expected is not None and labels["ticker"] not in expected:
            logger.warning(f"요청에 없는 ticker 응답 무시: {labels['ticker']}")
            continue
        out[labels["ticker"]] = labels
    return out


def judge_batch(stocks: list[dict]) -> dict[str, dict]:
    """종목 묶음 1회 판정. stocks 항목: {"ticker","name","items"}.

    반환: {ticker: labels} (실패·형식 불량은 빈 dict). 호출부는 결측을 NULL 로 저장한다.
    """
    blocks = [
        build_block(s["name"], s["ticker"], s.get("items") or [])
        for s in stocks
        if s.get("items")
    ]
    if not blocks:
        return {}
    prompt = NEWS_MATERIAL_PROMPT.format(blocks="\n\n".join(blocks))
    try:
        data = complete_json(prompt, temperature=0)
    except Exception as e:
        logger.warning(f"재료 지속성 판정 실패({len(blocks)}종목): {e}")
        return {}
    return parse_response(data, expected={s["ticker"] for s in stocks})


def judge_materials(stocks: list[dict], batch_size: int | None = None) -> dict[str, dict]:
    """종목 전건을 배치로 나눠 판정 — 한 배치 실패가 나머지를 막지 않는다.

    배치를 나누는 이유는 비용이 아니라 **JSON 응답 신뢰도**다(종목이 많으면 항목 누락이 늘고
    한 번의 파싱 실패로 전건을 잃는다). 배치당 입력은 종목 5일치 헤드라인이라 1~3k 토큰이다.
    """
    size = batch_size or NEWS_JUDGE_BATCH_SIZE
    out: dict[str, dict] = {}
    for i in range(0, len(stocks), max(1, size)):
        out.update(judge_batch(stocks[i:i + max(1, size)]))
    return out
