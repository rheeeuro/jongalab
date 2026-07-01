"""
AI 분석 서비스 모듈 - AI 클라이언트와 콘텐츠 분석 파이프라인 통합
"""
import logging
from dataclasses import dataclass, field
from ollama import Client

from core.config import OLLAMA_HOST, OLLAMA_MODEL, OPENAI_API_KEY, OPENAI_MODEL
from core.ai_utils import parse_ai_json


@dataclass
class AnalysisResult:
    """AI 분석 결과 통합 데이터 클래스"""
    title: str = ""
    content: str = ""
    sentiment_score: int = 50
    related_companies: list = field(default_factory=list)
    # 구조화 요약 필드 (B+C 고도화)
    tldr: str = ""                                   # 한 줄 대표 요약
    tags: list = field(default_factory=list)         # 테마 해시태그 ["#반도체", ...]
    summary: list = field(default_factory=list)      # 핵심 요약 불릿 3개
    stocks: list = field(default_factory=list)       # [{name,stance,conviction,horizon,reason}]
    strategy: str = ""                               # 대응 전략 한 줄


_STANCE_EMOJI = {"호재": "📈", "악재": "📉", "중립": "➖"}


def build_analysis_markdown(tldr: str, summary: list, stocks: list, strategy: str) -> str:
    """구조화 필드를 프론트/알림 호환용 Markdown 리포트로 재조립.

    LLM 은 구조화 JSON 만 내보내고, analysis_content(마크다운)는 여기서 만든다.
    기존 ContentCard(ReactMarkdown)·텔레그램 알림이 그대로 렌더되도록 섹션 구조를 유지한다.
    """
    parts: list[str] = []
    if tldr:
        parts.append(f"## 📌 한 줄 요약\n{tldr}")

    bullets = "\n".join(f"- {s}" for s in (summary or []) if s)
    if bullets:
        parts.append(f"## 1. 핵심 요약\n{bullets}")

    stock_lines: list[str] = []
    for s in stocks or []:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        stance = s.get("stance") or "중립"
        conviction = s.get("conviction") or ""
        horizon = s.get("horizon") or ""
        reason = (s.get("reason") or "").strip()
        emoji = _STANCE_EMOJI.get(stance, "")
        meta = "·".join(x for x in [stance, f"확신{conviction}" if conviction else "", horizon] if x)
        head = f"{emoji} **{name}**".strip()
        line = f"- {head} ({meta})" if meta else f"- {head}"
        if reason:
            line += f": {reason}"
        stock_lines.append(line)
    if stock_lines:
        parts.append("## 2. 주요 언급 종목\n" + "\n".join(stock_lines))

    if strategy:
        parts.append(f"## 3. 대응 전략\n> {strategy}")

    return "\n\n".join(parts)


_client = Client(host=OLLAMA_HOST)


def get_ai_client() -> Client:
    """공유 AI 클라이언트 인스턴스 반환"""
    return _client


def analyze_content(prompt: str, model: str | None = None, **chat_options) -> AnalysisResult | None:
    """
    프롬프트를 AI에 전달하고 파싱된 분석 결과를 반환.
    sentiment_score가 -1이거나 파싱 실패 시 None 반환.
    """
    model = model or OLLAMA_MODEL
    try:
        kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if chat_options:
            kwargs["options"] = chat_options

        response = _client.chat(**kwargs)
        raw_content = response["message"]["content"]
        data = parse_ai_json(raw_content)

        if data is None:
            logging.warning(f"⏭️ [스킵] AI 응답 JSON 파싱 실패. 원본 응답: {raw_content[:200]}")
            return None

        if data.get("sentiment_score") == -1:
            logging.info("⏭️ [스킵] AI가 주식 무관 콘텐츠로 판단 (sentiment_score: -1)")
            return None

        tldr = data.get("tldr", "") or ""
        tags = data.get("tags", []) or []
        summary = data.get("summary", []) or []
        stocks = data.get("stocks", []) or []
        strategy = data.get("strategy", "") or ""
        related = data.get("related_companies", []) or []
        # 하위호환: related_companies 가 비면 stocks 의 name 으로 채운다
        if not related and stocks:
            related = [s.get("name") for s in stocks if s.get("name")]

        # analysis_content(마크다운)는 구조화 필드로 재조립. 구 프롬프트 호환으로 content 가 오면 그대로 사용.
        content = data.get("content") or build_analysis_markdown(tldr, summary, stocks, strategy)

        result = AnalysisResult(
            title=data.get("title", ""),
            content=content,
            sentiment_score=data["sentiment_score"],
            related_companies=related,
            tldr=tldr,
            tags=tags,
            summary=summary,
            stocks=stocks,
            strategy=strategy,
        )
        logging.info(
            f"🔍 AI 분석 결과: score={result.sentiment_score}, "
            f"companies={result.related_companies}, stocks={len(result.stocks)}"
        )
        return result

    except KeyError as e:
        logging.error(f"AI 분석 에러: 응답에 필수 키 누락 - {e}")
        return None
    except Exception as e:
        logging.error(f"AI 분석 에러: {e}")
        return None


_openai_client = None


def _get_openai_client():
    """OpenAI 클라이언트 지연 초기화 (키 없으면 사용처에서만 실패하도록)."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def complete_json(prompt: str, *, model: str | None = None, temperature: float = 0.1) -> dict | None:
    """OpenAI(GPT)에 프롬프트를 보내 JSON 응답을 파싱해 dict 로 반환 (실패 시 None).

    일일 다이제스트와 동일하게 OpenAI 를 쓰되, 워커가 SDK 를 직접 부르지 않도록 이 추상화를 경유한다.
    구조화된 의사결정(예: 주간 가중치 튜닝 제안)에 사용.
    """
    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=model or OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        raw_content = response.choices[0].message.content
        logging.info(f"GPT 원본 응답:\n{raw_content}")
        return parse_ai_json(raw_content)
    except Exception as e:
        logging.error(f"GPT 응답 에러: {e}")
        return None
