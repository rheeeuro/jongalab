"""뉴스 '재료 지속성' 벌크 판정 (OpenAI, ai_service.complete_json 경유).

## 왜 이 모듈이 있나
종가베팅은 종가 매수 → 익일 개장 청산이라, **내일 아침에 살 사람이 있어야** 갭상승이 나온다.
그래서 이 모듈이 판정하는 것은 재료의 성질 자체가 아니라 한 가지 질문이다 —
**"오늘 이 재료를 본 사람이 내일 아침에도 이 종목을 살 만한가."**
가설은 **"수치가 이미 확정된 단발 이벤트는 종가에 소진되고(내일 살 이유가 없다), 다음 마일스톤이
남은 연속 재료는 익일까지 이어진다(내일도 기대를 산다)"** 이다.
→ **판정의 자는 익일 아침이다**: 지속성 rule 의 `exit_label` 은 전부 `exec_leg_ret`(종가 진입 →
익일 아침 청산 = 갭 실현치)이다. `mat_run_ret_3d`(D+3, sql/53)는 "재료가 실제로 계속 먹혔나"를
되짚는 **보조 정답지**이고 승격 판정의 자가 아니다(현행 전략은 익일 아침에 전량 청산한다).
실측 단서(2026-07-01~27, next_open_ret 기준, n 이 작아 근거는 아님):

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
대상이 없다). 그래서 **관측 가능한 사실 축**으로 쪼개 묻고, 지속성 등급은 코드가 결정론적으로
합성한다(`derive_durability`) — 판정 근거가 어디서 틀렸는지 육안 감사가 되고, 합성 규칙을
바꿔도 과거 라벨을 재해석할 수 있다.
  next_milestone    — 재료에 다음 예정 사건이 남았나 (허가 결정·본계약·예산 집행·다음 임상 단계)
  milestone_horizon — 그 사건이 **언제** 오나 (1주내/1개월내/그이후/불명) ← v2 신규
  amount_locked     — 수치가 이미 확정·소진됐나 (실측 무차별 → 합성에서 제외, 수집은 유지)
  material_size_eok — 재료의 금액 규모(억원). 코드가 시총으로 나눠 비율 파생 ← v2 신규
  driver_scope      — 종목 단독인가 산업·정책 사이클인가 (사이클이면 후속·동종주 확산이 붙음)
  stage             — 재료 사이클의 첫 발표 / 진행 / 마무리 (마무리 = 소진)
합성 규칙 버전은 `DURABILITY_VERSION` 으로 라벨과 함께 저장한다 — 같은 컬럼에 다른 뜻의 라벨이
섞이면 rule 채점 표본이 조용히 오염된다.

## 판정 근거는 '5일치' 헤드라인 + 리드문 발췌다
당일 헤드라인만으로는 `stage`(첫 발표인지 세 번째 후속인지)를 알 수 없다. 종목별로 최근
NEWS_JUDGE_LOOKBACK_DAYS 일치를 날짜와 함께 묶어 넣는다.
2026-08-05 부터 **리드문 발췌**(news_mention.body_preview, 네이버 종목별 경로)가 붙는다 —
그 전까지는 본문이 없어 마일스톤 '날짜'와 재료 '규모'를 판정할 수 없어서 마일스톤은 '존재
여부'만 물었고, 그 결과 `next_milestone=1` 집단에 '내일 결정'과 '내년 어느 날'이 같이 들어갔다.
코퍼스에서 **시세보도는 뺀다**(`is_price_report`) — 재료가 아니고, 네이버 소스를 텍스트
게이트에 넣으면서 "급락·약세" 기사가 sentiment 를 끌어내려 live veto 를 오발동시키는 경로를
막는다(select_headlines 주석).

돈이 걸린 판정이 아니라 연구 라벨이지만, 하루 16종목 전건 판정에는 처리량이 필요해
로컬 Ollama(건당 100~300초, 하루 5행 상한이 이 병목이었다) 대신 OpenAI 를 쓴다.
**이 모듈이 예전 `core/news_summary.py`(Ollama 단건 요약)를 대체한다** — 같은 컬럼
(news_summary/news_sentiment/news_catalyst)을 채우므로 두 경로를 남기면 어느 쪽이 라벨을
만들었는지 알 수 없어 그 파일은 삭제했다.
프롬프트는 가드 파일(core/prompts.py)이 아니라 여기 둔다(news_veto_judge 선례).
모델은 OPENAI_MODEL 단일 출처를 따른다 — 2026-08-05 gpt-5.4-nano → gpt-5.6-luna(비용 동일,
축 커버리지 개선: 실측 52종목 stage='불명' 15→5건). **모델을 바꾸면 등급 정의를 바꾼 것과 같이
표본을 분리한다**(라벨 분포가 바뀐다 — 미판정 15→5·연속 9→18·소진 17→13, sentiment 평균 +11):
지속성·재료 rule 의 registered_at 을 교체일로 리셋한다(sql/54 선례, 교체분은 sql/58).

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
# 촉매 시점 — '다음 예정 사건이 언제인가'. 종가베팅은 하루 보유라 '내일 결정'과 '내년 어느 날'은
# 완전히 다른 재료인데, v1 은 마일스톤의 **존재 여부**만 물어 둘을 한 집단에 넣었다.
MILESTONE_HORIZONS = ("1주내", "1개월내", "그이후", "불명")

# 지속성 합성 규칙 버전 — daily_stock_report.news_durability_v 에 함께 저장한다.
# 같은 컬럼에 다른 뜻의 라벨이 섞이면 rule 채점 표본이 조용히 오염된다(v1 표본으로 통과한
# 룰이 v2 라벨로 계속 평가되는 상황). 버전이 있으면 표본을 분리하고, 사실 축이 남아 있으므로
# 규칙을 바꿔도 과거 라벨을 소급 재합성할 수 있다.
DURABILITY_VERSION = 2

# 시세보도 헤드라인 판별 — '재료'가 아니라 그날 가격 움직임을 옮긴 기사다.
# 후속 재료 실현 채점(count_followup_days)에서 제외해야 한다: 갭상승이 "XX 급등" 기사를 만드는
# 역인과라, 이걸 후속 재료로 세면 "재료가 이어졌다"가 "어제 올랐다"의 동어반복이 된다
# (실측 2026-07-14~27 익일 아침 헤드라인 449건 중 95건 = 21% 가 이 부류).
# 평범한 '상승/하락'은 넣지 않는다 — "수출 상승" 같은 재료 기사까지 배제된다.
_PRICE_REPORT_RE = re.compile(
    r"급등|급락|상한가|하한가|강세|약세|치솟|폭등|폭락|↑|↓|신고가|신저가|장중|특징주|시황"
)

NEWS_MATERIAL_PROMPT = """당신은 한국 주식 재료 분석가다. 아래는 여러 종목의 최근 뉴스 속보 헤드라인이다(종목별, 날짜 오름차순).

[무엇을 판정하는가 — 이 판정의 목적]
우리는 오늘 종가에 사서 **내일 아침에 파는** 전략을 쓴다. 그래서 유일하게 중요한 질문은
**"오늘 이 재료를 본 사람이 내일 아침에도 이 종목을 살 만한가"** 이다.
재료가 오늘로 끝났으면 내일 아침 살 사람이 없고(= 갭상승이 안 나온다), 아직 남은 일정이 있고
그 결과가 곧 나오면 내일 아침에도 기대를 사는 사람이 있다. 아래 항목들은 그 판단을 **감(感)이
아니라 사실로 쪼개어** 묻는 것이다. 각 항목은 헤드라인·리드문에 적힌 내용으로만 답하라.
주가 전망·목표가는 말하지 말고, 재료의 사실 관계만 판정하라(등급은 코드가 합성한다).

[판정 기준]
- next_milestone: 이 재료에 **아직 남은 다음 예정 사건**이 있으면 1, 없으면 0.
  1 예: FDA 실사 종결(→ 허가 결정 남음), MOU·수주 협의(→ 본계약 남음), 정책 발표(→ 예산 집행·후속 법안), 임상 1상 성공(→ 2상), 증설 착공(→ 가동)
  0 예: 계약 체결 완료, 실적 발표 완료, 지분 매각 완료, 이미 종결된 소송 판결
- milestone_horizon: 그 **다음 예정 사건이 언제** 오는가. 헤드라인·리드문에 적힌 시점 표현만 근거로 하라(추측 금지).
  "1주내"  : 날짜가 이번 주·다음 주로 명시됐거나 "이달 말 결정", "내일 발표", "오는 O일" 처럼 임박
  "1개월내": "내달", "다음 분기 초", "연내 상반기" 처럼 한 달 안으로 읽히는 시점
  "그이후" : "내년", "2027년", "장기 과제", "향후 수년" 처럼 먼 시점
  "불명"   : 시점 표현이 아예 없거나 next_milestone 이 0/null
- amount_locked: 재료의 수치·규모가 **이미 확정되어 더 늘 여지가 없으면** 1, 누적·확대 여지가 있으면 0.
  1 예: "1,200억 수주 계약 체결", "2분기 영업이익 3,000억 확정", 유상증자 발행가액 확정
  0 예: 수주잔고 누적 중, 파이프라인 진행 중, 정책 예산 규모 미정, 증설 램프업 진행
- material_size_eok: 재료의 **금액 규모를 억원 단위 정수**로. 텍스트에 금액이 적혀 있을 때만 채우고 없으면 null.
  "1,200억 수주" → 1200 / "3조 원 투자" → 30000 / "영업이익 3,000억" → 3000 / "5,219억 규모" → 5219
  **원 단위가 아니라 억원이다**(0 을 붙이지 마라). 주가·시가총액·지분율은 재료 규모가 아니다(null).
  여러 금액이 있으면 그 재료의 핵심 금액 하나만.
- driver_scope: 재료의 동인이 그 회사만의 사건이면 "종목단독", 산업·정책 사이클(동종업계가 함께 움직이는 성질)이면 "산업사이클", 불분명하면 "불명"
- stage: 이 재료가 헤드라인에 처음 등장했으면 "첫발표", 후속 보도·진행 경과면 "진행", 마무리·종결 국면이면 "마무리", 불분명하면 "불명"
- sentiment_score: 재료 방향 0~100 정수 (호재>50, 악재<50, 중립=50)
- catalyst_type: 실적 | 수주계약 | 임상승인 | M&A | 정책테마 | 증자감자 | 지분변동 | 기타 중 하나.
  **종목마다 독립적으로 판정하라**(다른 종목의 유형을 그대로 옮기지 마라).
  `정책테마`는 **정부 정책·규제·국책사업·국가 간 협정**에 한정한다 — 민간 기업 간 협력·제휴·공급가
  인상·기술 협약은 정책이 아니다(딱 맞는 유형이 없으면 억지로 고르지 말고 `기타`).
- ⚠️ **재료가 여러 개면 주가를 가장 크게 움직일 주된 재료 하나를 골라 그것만 판정하라.**
  "재료가 여러 개라서" 또는 "어느 재료인지 애매해서" 를 보류 사유로 쓰지 마라 — 대형주는 하루에
  여러 기사가 나는 게 정상이고, 그때 판정을 비우면 그 종목은 영원히 라벨이 없다. 골랐으면
  summary 에 어느 재료를 골랐는지 밝혀라.
- 이 종목이 뉴스의 **직접 당사자가 아닐 때만**(시황·경쟁사 기사에 곁다리로 언급되었을 때만)
  next_milestone·amount_locked 를 null 로, stage·driver_scope 를 "불명"으로 두라.
  당사자인데 다음 사건 여부가 텍스트에서 안 읽히면 next_milestone 은 **0**(남은 사건이 확인되지
  않음)이다 — null 은 '이 기사는 이 종목 재료가 아니다'라는 뜻으로만 쓴다.
- ⚠️ `summary`·`reason` 은 **사이트 리포트 화면에 그대로 노출되는 문장**이다(내부 로그가 아니다).
  위 항목 이름과 코드값은 판정에만 쓰고 문장에는 절대 넣지 마라 — 우리말로 풀어 써라.

[종목별 헤드라인] (일부 기사에는 제목 뒤에 `/` 로 리드문 발췌가 붙어 있다 — 시점·금액 근거로 쓰라)
{blocks}

아래 JSON 형식으로만 답하라. items 에는 위 종목 전부를 ticker 그대로 포함하라.
{{
  "items": [
    {{
      "ticker": "<종목코드 6자리>",
      "sentiment_score": <0~100 정수>,
      "catalyst_type": "<재료 유형>",
      "next_milestone": <1 | 0 | null>,
      "milestone_horizon": "<1주내 | 1개월내 | 그이후 | 불명>",
      "amount_locked": <1 | 0 | null>,
      "material_size_eok": <억원 단위 정수 | null>,
      "driver_scope": "<종목단독 | 산업사이클 | 불명>",
      "stage": "<첫발표 | 진행 | 마무리 | 불명>",
      "summary": "<재료 핵심 2~3줄 한글 요약. 마크다운 불필요>",
      "reason": "<지속성 판정 근거 한 문장. 근거 헤드라인을 인용하라. **투자자가 읽는 문장이다** — 위 판정 항목 이름(next_milestone·amount_locked·driver_scope·stage)이나 코드값(=1/=0/null)을 문장에 쓰지 말고 '다음 예정 사건이 남아 있다 / 없다', '규모가 수치로 확정됐다 / 아직 늘 여지가 있다', '판단을 보류한다' 처럼 우리말로 풀어 쓰라>"
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

    **시세보도는 코퍼스에서 뺀다**(2026-08-05, `is_price_report`). 두 가지 이유:
      ① 재료가 아니다 — "XX 급등"은 그날 가격을 옮긴 기사라 지속성 축의 근거가 못 된다.
         상한 20건을 이런 기사가 먹으면 정작 재료 기사가 잘린다(네이버 코퍼스는 종목당
         하루 ~45건이라 상한이 늘 걸린다).
      ② **오탐 차단** — 네이버 소스를 텍스트 게이트에 넣으면서 "급락·약세·폭락" 기사가 대량
         유입되는데, 이게 `sentiment_score` 를 끌어내리면 `veto_bad_news`(live, 자금 경로)가
         '재료 악재'가 아니라 '어제 빠졌다'로 발동한다. 그 경로를 여기서 끊는다.
    남는 기사가 없으면 빈 리스트를 돌려준다 → 그 종목은 프롬프트 블록에서 빠지고 라벨 없음
    (NULL = rule 미개입)이 된다. 시세보도만 난 종목은 애초에 판정할 재료가 없다.
    """
    seen: set[str] = set()
    rows: list[dict] = []
    for it in items:
        headline = (it.get("headline") or "").strip()
        if not headline or is_price_report(headline):
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
        # 같은 날짜 예산 안에서는 **리드문이 있는 기사를 먼저** 넣는다(2026-08-05).
        # 시점(milestone_horizon)·금액 축은 제목에 거의 안 실려 리드문이 유일한 근거인데,
        # 최신순으로만 자르면 리드문 없는 텔레그램 헤드라인이 예산을 먹는다 — 실측: 리드문이
        # 8종목분만 있던 실행에서 horizon 이 17/17 전부 '불명' 이었고, 리드문이 붙은 코퍼스로
        # 같은 프롬프트를 돌리자 불명 14·그이후 6·1개월내 2 로 축이 살아났다.
        # 정렬은 안정(stable)하므로 리드문 유무가 같으면 원래의 최신순이 유지된다.
        day_items = sorted(by_day[day], key=lambda it: bool(it.get("body_preview")))
        for it in day_items[-per_day:]:
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


# 프롬프트에 넣는 리드문 길이 상한. 저장은 500자까지 하되(원자료 보존) 프롬프트는 자른다 —
# 8종목 × 20건이 한 배치라 발췌를 그대로 넣으면 입력이 배치당 14k 토큰까지 늘어난다.
# 실측 리드문은 ~135자이므로 140 이면 대부분 온전히 들어간다.
_BODY_PROMPT_MAX = 140


def build_block(name: str, ticker: str, items: list[dict]) -> str:
    """종목 1개의 프롬프트 블록 — 날짜 오름차순 헤드라인 묶음(날짜 분산 선별).

    리드문 발췌가 있으면 `제목 / 발췌` 로 붙인다(네이버 경로만 있고 텔레그램은 없다).
    시점(`milestone_horizon`)·금액(`material_size_krw`) 축은 제목에 거의 안 실려서 이 발췌가
    유일한 근거다 — 없으면 그 축은 불명/null 로 남는다(억지 추정 금지를 프롬프트가 명시).
    """
    rows = select_headlines(items, NEWS_JUDGE_MAX_HEADLINES, NEWS_JUDGE_LOOKBACK_DAYS)
    lines = []
    for it in rows:
        line = f"- ({it.get('d')}) {it['headline'].strip()}"
        body = (it.get("body_preview") or "").strip()
        if body:
            line += f" / {body[:_BODY_PROMPT_MAX]}"
        lines.append(line)
    return f"## {name}({ticker})\n" + "\n".join(lines)


def derive_durability(labels: dict) -> str | None:
    """사실 축 → 지속성 등급('연속'/'중립'/'소진'). 판정 불가면 None. (규칙 v2, 2026-08-05)

    여기서 '지속성'은 **주가를 이어서 올려줄 수 있는 성질**이다(재료 언급이 계속되는 것과 다르다 —
    언급의 지속은 이미 시총 프록시로 판명났다).

    **순서가 곧 우선순위다**(disclosure_events._RULES 와 같은 규약):
      1. stage='마무리'                        → 소진 (마무리 국면은 남은 게 없다)
      2. next_milestone=1 & 촉매 1개월 내       → 연속 (다음 사건이 남고 **임박**했다)
      3. next_milestone=1 & 산업사이클          → 연속 (사이클 재료는 후속·동종주 확산이 붙는다)
      4. next_milestone=1                      → 중립 (사건은 남았지만 시점이 멀거나 불명)
      5. next_milestone=0 & stage 판정됨        → 소진 (다음 사건이 없다 = 단발)
      6. 그 외(next_milestone 결측 / '소진'인데 stage 불명) → None

    **5번의 비대칭 — '소진'만 stage 를 요구하는 이유**: '연속'은 "다음 사건이 있다"는 긍정
    진술이라 근거(milestone+시점)만 있으면 성립하지만, '소진'은 "다음에 올려줄 게 없다"는
    **부정 진술**이라 재료가 특정됐을 때만 유효하다. stage='불명'(재료 특정 실패)인데 소진으로
    확정하면 "모르겠다"를 "없다"로 바꿔 적는 억지 라벨이 되고, 그 표본으로 `veto_news_spent`
    를 채점하면 배제 대상이 유니버스 대부분으로 부풀어 veto 의 뜻 자체가 사라진다
    (실측 2026-08-05 프로브: 이 가드가 없으면 판정 6건 중 5건이 전부 '소진'으로 몰렸다).

    ── v1 대비 바뀐 것과 근거 (2026-07-29~08-03 실측, 익일 시가 같은 날 초과수익) ──
    · `amount_locked` 를 합성에서 **빼냈다**: locked=1 −0.13%p / locked=0 +0.15%p 로 실측
      무차별이었다. 그런데 v1 에서는 이 축이 '연속' 판정의 필수 조건이라(규칙 2) 유효한 축인
      `next_milestone`(+0.70%p) 을 가리고 있었다. 축 자체는 계속 수집한다(재해석 가능).
    · `milestone_horizon` 을 넣었다: 종가베팅은 하루 보유라 '내일 결정'과 '내년 어느 날'이 같은
      집단에 있으면 안 된다. v1 의 `next_milestone=1` 집단에 그 둘이 섞여 있었다.
    · `stage` 결측('불명')을 더 이상 **차단하지 않는다**: v1 은 stage 가 불명이면 전부 None 이라
      라벨 커버리지를 깎았는데, 실측에서 stage='불명' 집단은 오히려 +1.15%p(t=1.31) 로 나쁘지
      않았다. '마무리'만 판정에 쓰고(그게 t=-2.79 로 유일하게 유의한 신호다) 나머지 불명은
      milestone 축으로 판정한다.
    필수 축(`next_milestone`)이 결측이면 **None** 이다 — 라벨을 억지로 만들면 rule 이 결측을
    '중립'으로 오인해 표본이 오염된다(predicate 는 NULL 을 매칭 실패로 처리하므로 안전한 기본값).
    프롬프트가 '당사자가 아니거나 재료 특정 불가면 null' 을 명시하므로, 곁다리 언급은 여기서
    자동으로 라벨 없음이 된다.
    """
    milestone = labels.get("next_milestone")
    if milestone is None:
        return None
    stage = labels.get("stage")
    if stage == "마무리":
        return "소진"
    if milestone == 1:
        if labels.get("milestone_horizon") in ("1주내", "1개월내"):
            return "연속"
        if labels.get("driver_scope") == "산업사이클":
            return "연속"
        return "중립"
    if not stage or stage == "불명":
        return None      # 재료 특정 실패 — '없다'고 단정할 근거가 없다(위 비대칭 주석)
    return "소진"


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
    horizon = str(item.get("milestone_horizon") or "").strip()
    if horizon not in MILESTONE_HORIZONS:
        horizon = "불명"

    # 재료 금액 — **억원** 단위 정수만 받는다. 문자열("1200억")·음수·비현실적 값은 버린다(None).
    # 상한 1,000만 억원(=1,000조): 시총 최대(삼성전자 ~1,450조)에 준하는 선으로, 자릿수 착오를
    # 걸러내면서 실제 합병·국책사업 규모는 통과시킨다. 원 단위로 물었을 때 "5,219억"을 5.219조로
    # 뽑는 10배 착오가 실측돼 단위를 억원으로 바꿨다(edge_features.material_size_ratio 주석).
    size = item.get("material_size_eok")
    if isinstance(size, bool) or not isinstance(size, (int, float)):
        size = None
    elif not (0 < size <= 10_000_000):
        size = None
    else:
        size = int(size)

    labels = {
        "ticker": ticker,
        "sentiment": sentiment,
        "catalyst": catalyst or None,
        "next_milestone": _flag("next_milestone"),
        "milestone_horizon": horizon,
        "amount_locked": _flag("amount_locked"),
        "material_size_eok": size,
        "driver_scope": scope,
        "stage": stage,
        "summary": (str(item.get("summary") or "").strip() or None),
        "reason": (str(item.get("reason") or "").strip()[:255] or None),
    }
    labels["durability"] = derive_durability(labels)
    labels["durability_v"] = DURABILITY_VERSION if labels["durability"] else None
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
