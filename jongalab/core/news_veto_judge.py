"""보유 종목 밤사이 중대 악재 판정 (OpenAI, ai_service.complete_json 경유).

종가베팅 포지션은 다음 날 아침 정상 흐름(NXT 08:03 반매도 → 09:28 전량청산)으로 정리되지만,
밤사이 '시초가 갭하락이 거의 확실한 중대 악재'(FDA 승인 실패, 대형 계약 파기 등)가 터진 종목은
그 흐름을 기다리지 않고 개장 즉시 전량 손절해야 손실이 준다(HLB 하한가 사건 교훈).
여기서는 news_mention 헤드라인만 근거로 severe 여부를 판정한다 — workers/news_guard.py 가
news_veto_verdict 에 기록하면 trading monitor 가 severe=1 종목을 개장 즉시 전량 매도한다.

돈이 걸린 판정이라 로컬 Ollama 가 아닌 OpenAI(complete_json)를 temperature=0 으로 쓴다.
프롬프트는 가드 파일(core/prompts.py)이 아니라 여기 둔다 — 뉴스 판정 프롬프트는 쓰는 모듈에
같이 두는 것이 이 프로젝트 관례다(core/news_material_judge.py 도 동일).
오탐 완충: severe 발동은 confidence >= NEWS_GUARD_MIN_CONFIDENCE 일 때만(is_actionable) —
오탐 비용은 '그날 갭상승 이익 상실' 정도로 제한적(어차피 당일 오전 전량청산)이지만,
확신 낮은 판정으로 프리마켓 얇은 호가에 던지는 것은 피한다.
"""
import logging
from datetime import datetime, time, timedelta

from core.ai_service import complete_json
from core.config import NEWS_GUARD_MIN_CONFIDENCE
from core.market_calendar import is_trading_day

logger = logging.getLogger("NewsVetoJudge")

# 판정 분류 화이트리스트 — LLM 이 목록 밖 값을 내면 '해당없음'으로 강제(컬럼 VARCHAR(20) 보호 겸용)
VETO_CATEGORIES = ("임상실패", "계약파기", "횡령배임", "거래정지", "규제제재", "증자희석", "사고재해", "해당없음")

NEWS_VETO_PROMPT = """당신은 한국 주식 리스크 심사역이다. 아래는 오버나잇 보유 중인 '{name}'({ticker}) 종목에 대해
전일 장 마감 무렵 이후 수집된 뉴스 속보 헤드라인이다(시간순). 오늘 시초가 갭하락이 거의 확실한
'중대 악재'가 터졌는지만 판정하라. 헤드라인에 명시된 사실만 근거로 하고 추측·확대해석은 금지한다.
반드시 이 기업이 뉴스의 직접 당사자여야 한다(경쟁사·동종업계·시황 뉴스는 해당 없음).

[중대 악재 (severe=true)]
- FDA/식약처 승인 실패·반려(CRL), 임상시험 실패·중단
- 대규모 수주계약 해지·파기·수주 실패, 핵심 고객 이탈
- 횡령·배임·분식회계 혐의, 검찰 압수수색
- 거래정지, 감사의견 거절, 상장폐지 사유 발생, 금감원 감리 착수
- 대형 리콜·화재·사고로 핵심 설비/제품 손실
- 대규모 유상증자·CB 발행 기습 공시(주주가치 희석)

[중대 악재 아님 (severe=false)]
- 증권사 목표가·투자의견 하향, 단순 하락 전망·경고성 해설
- 경쟁 심화·업황 우려·시황성 기사
- 소폭 실적 부진, 이미 여러 날 반복 보도된 악재의 재탕
- 다른 기업이 주체인 뉴스에 곁다리로 언급된 경우

[헤드라인]
{headlines}

아래 JSON 형식으로만 답하라:
{{
  "severe": true 또는 false,
  "confidence": <0~100 정수 — 판정 확신도>,
  "category": "<임상실패 | 계약파기 | 횡령배임 | 거래정지 | 규제제재 | 증자희석 | 사고재해 | 해당없음>",
  "reason": "<판정 근거 한두 문장, 한글>",
  "evidence": ["<근거가 된 헤드라인 원문 1~3개>"]
}}"""


def news_window_start(now: datetime) -> datetime:
    """판정에 쓸 뉴스 창의 시작 = 전거래일 15:00 (매수 창 KRX 15:00 시작 시점).

    매수 직전 오후에 터진 악재도 포함한다(의도 — 선정 로직이 놓친 악재의 최종 방어).
    주말·공휴일은 건너뛴다: 월요일 아침이면 금요일 15:00부터 주말 내내의 뉴스가 창에 들어온다.
    """
    d = now.date() - timedelta(days=1)
    while not is_trading_day(datetime.combine(d, time(12, 0))):
        d -= timedelta(days=1)
    return datetime.combine(d, time(15, 0))


def validate_verdict(data: dict | None) -> dict | None:
    """LLM 응답을 검증·정규화한 판정 dict 로 (실패 시 None → 호출부가 다음 폴링에 재시도).

    severe 가 발동 후보(True)인데 confidence 를 못 읽으면 통째로 무효 처리한다 —
    확신도 없는 severe 로 매도를 트리거하지 않기 위함.
    """
    if not isinstance(data, dict):
        return None
    severe = data.get("severe")
    if isinstance(severe, str):
        low = severe.strip().lower()
        if low not in ("true", "false"):
            return None  # "maybe" 류 애매한 값은 False 로 뭉개지 않고 무효 처리
        severe = low == "true"
    if not isinstance(severe, bool):
        return None
    try:
        confidence = max(0, min(100, int(data.get("confidence"))))
    except (TypeError, ValueError):
        return None
    category = str(data.get("category") or "").strip()
    if category not in VETO_CATEGORIES:
        category = "해당없음"
    evidence = [str(e) for e in data.get("evidence") or [] if e][:3]
    return {
        "severe": severe,
        "confidence": confidence,
        "category": category,
        "reason": str(data.get("reason") or "").strip()[:500],
        "evidence": evidence,
    }


def is_actionable(verdict: dict | None) -> bool:
    """이 판정으로 실제 전량매도를 트리거할지 — severe + 확신도 게이트."""
    return bool(verdict) and verdict["severe"] and verdict["confidence"] >= NEWS_GUARD_MIN_CONFIDENCE


def judge_headlines(name: str, ticker: str, rows: list[dict]) -> dict | None:
    """헤드라인 묶음 1회 판정. rows: get_news_since 결과([{headline, channel_name, created_at}]).

    반환: validate_verdict 통과 dict | None(LLM 실패·형식 불량 — 기록하지 않고 재시도 가치 있음).
    """
    if not rows:
        return None
    lines = []
    for r in rows:
        ts = r.get("created_at")
        stamp = ts.strftime("%m-%d %H:%M") if isinstance(ts, datetime) else ""
        lines.append(f"- [{r.get('channel_name') or '?'} {stamp}] {r.get('headline') or ''}")
    prompt = NEWS_VETO_PROMPT.format(name=name, ticker=ticker, headlines="\n".join(lines))
    data = complete_json(prompt, temperature=0.0)
    verdict = validate_verdict(data)
    if verdict is None:
        logger.warning("뉴스 베토 판정 실패/형식 불량 [%s] — 다음 폴링 재시도", ticker)
    return verdict
