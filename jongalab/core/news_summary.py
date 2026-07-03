"""후보 종목 뉴스 재료 배치 요약 (Ollama, ai_service 재사용).

뉴스 전량(1000+/일)은 LLM 없이 사전매칭만 하고(news_matcher), 여기서는 closing_bet Phase 2 를
통과한 '소수 후보' 중 뉴스가 몰린 종목의 헤드라인 묶음만 1회 요약한다. LLM 예산을 재료가
실제로 의미 있는 지점(선정 후보)에만 쓴다.

요약과 함께 재료 방향(sentiment 0~100)·재료 유형(catalyst)을 라벨링한다 — 같은 1회 호출의
출력 필드만 늘린 것이라 LLM 비용은 종전과 동일하다. 라벨은 daily_stock_report 에 저장되어
next_open_ret 과 조인한 뉴스 팩터 엣지 검증에 쓰인다(점수 무영향).

프롬프트는 가드 파일(core/prompts.py)이 아니라 여기 둔다 — 뉴스 요약 전용이라 민감 로직과 분리.
호출은 반드시 ai_service.analyze_content() 추상화를 경유한다(직접 SDK 호출 금지).
"""
import logging

from core.ai_service import analyze_content

logger = logging.getLogger("NewsSummary")

# 재료 유형 화이트리스트 — LLM 이 목록 밖 값을 내면 '기타'로 강제(컬럼 VARCHAR(20) 보호 겸용)
CATALYST_TYPES = ("실적", "수주계약", "임상승인", "M&A", "정책테마", "증자감자", "지분변동", "기타")

NEWS_SUMMARY_PROMPT = """당신은 한국 주식 뉴스 분석가다. 아래는 오늘 '{name}'({ticker}) 종목이 언급된 뉴스 속보 헤드라인 모음이다.
이 종목의 '오늘 재료'가 무엇인지 헤드라인에 근거해서만 요약하라. 헤드라인에 없는 내용은 추측하지 마라.

[헤드라인]
{headlines}

아래 JSON 형식으로만 답하라:
{{
  "sentiment_score": <0~100 정수. 재료가 호재면 50 초과, 악재면 50 미만, 중립이면 50>,
  "catalyst_type": "<재료 유형 하나만: 실적 | 수주계약 | 임상승인 | M&A | 정책테마 | 증자감자 | 지분변동 | 기타>",
  "content": "<재료 핵심을 2~3줄로 요약한 한글 문장. 마크다운 불필요>"
}}"""


def summarize_news(name: str, ticker: str, headlines: list[str]) -> dict | None:
    """헤드라인 묶음을 1회 요약해 재료 라벨을 반환. 실패 시 None.

    반환: {"content": 요약 문장, "sentiment": 0~100 | None, "catalyst": 유형 | None}
    """
    if not headlines:
        return None
    joined = "\n".join(f"- {h}" for h in headlines if h)
    prompt = NEWS_SUMMARY_PROMPT.format(name=name, ticker=ticker, headlines=joined)
    try:
        result = analyze_content(prompt)
    except Exception as e:
        logger.warning(f"뉴스 요약 실패 [{name}]: {e}")
        return None
    if not result or not result.content:
        return None

    sentiment = result.sentiment_score
    if not isinstance(sentiment, int) or not (0 <= sentiment <= 100):
        sentiment = None

    catalyst = (result.raw.get("catalyst_type") or "").strip()
    if catalyst and catalyst not in CATALYST_TYPES:
        catalyst = "기타"

    return {
        "content": result.content.strip(),
        "sentiment": sentiment,
        "catalyst": catalyst or None,
    }
