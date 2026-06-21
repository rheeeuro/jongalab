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

        result = AnalysisResult(
            title=data.get("title", ""),
            content=data["content"],
            sentiment_score=data["sentiment_score"],
            related_companies=data.get("related_companies", []),
        )
        logging.info(
            f"🔍 AI 분석 결과: score={result.sentiment_score}, "
            f"companies={result.related_companies}"
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
