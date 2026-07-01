"""뉴스 헤드라인 → 종목 사전매칭 (LLM 없음).

고빈도 뉴스 채널(하루 1000+건)은 메시지마다 LLM 분석이 불가하므로, ticker_dictionary(ACTIVE)
의 기업명을 인메모리 매처로 로드해 헤드라인에서 등장 종목만 값싸게 뽑는다.

매칭 정밀도:
- 한글엔 단어 경계가 없어 부분일치 오탐이 잦다. 기업명 앞뒤가 '한글/영숫자'가 아닌 경우만
  매칭(경계 룩어라운드)해 '삼성' 이 '삼성전자' 안에서 잡히는 것을 막는다.
- 대안(alternation)을 긴 이름부터 정렬해 같은 위치에서 더 긴 사명이 우선 매칭되게 한다.
- 뉴스는 종합점수 가중치 0(표시·튜닝 전용)이라 오탐은 '화면 노이즈'일 뿐 손실과 무관하다.

사전은 프로세스 기동 시 1회 로드하고 REFRESH_SECONDS 마다 갱신(시딩 워커가 채운 신규 종목 반영).
"""
import re
import time
import logging

from core.repository.ticker import get_ticker_dictionary

logger = logging.getLogger("NewsMatcher")

# 2글자 미만(초성/약어)은 오탐이 심해 제외
MIN_NAME_LEN = 2
# 사전 갱신 주기(초). 시딩 워커가 ACTIVE 종목을 채우면 다음 갱신에 반영된다.
REFRESH_SECONDS = 3600

# 앞뒤가 한글/영문/숫자가 아니어야 매칭 (토큰 경계 근사)
_BOUNDARY_L = r"(?<![가-힣A-Za-z0-9])"
_BOUNDARY_R = r"(?![가-힣A-Za-z0-9])"

_pattern: re.Pattern | None = None
_name_to_ticker: dict[str, str] = {}
_loaded_at: float = 0.0


def _build(entries: list[dict]) -> tuple[re.Pattern | None, dict[str, str]]:
    name_to_ticker: dict[str, str] = {}
    for row in entries:
        name = (row.get("company_name") or "").strip()
        ticker = (row.get("ticker_symbol") or "").strip()
        if len(name) < MIN_NAME_LEN or not ticker:
            continue
        # 같은 이름 중복 시 먼저 온 것 유지(get_ticker_dictionary 는 ACTIVE 우선 정렬 아님 →
        # 중복 사명은 거의 없고, 있으면 임의 1개로 충분)
        name_to_ticker.setdefault(name, ticker)

    if not name_to_ticker:
        return None, {}

    # 긴 이름부터 정렬 → 같은 위치에서 더 긴 사명이 우선 매칭
    names_sorted = sorted(name_to_ticker.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(n) for n in names_sorted)
    pattern = re.compile(f"{_BOUNDARY_L}({alternation}){_BOUNDARY_R}")
    return pattern, name_to_ticker


def _ensure_loaded(force: bool = False) -> None:
    global _pattern, _name_to_ticker, _loaded_at
    now = time.time()
    if not force and _pattern is not None and (now - _loaded_at) < REFRESH_SECONDS:
        return
    try:
        entries = get_ticker_dictionary(status="ACTIVE")
        pattern, mapping = _build(entries)
        if pattern is None:
            logger.warning("ACTIVE 종목 사전이 비어있음 — 뉴스 매칭 불가(시딩 워커 확인)")
            _pattern, _name_to_ticker = None, {}
        else:
            _pattern, _name_to_ticker = pattern, mapping
            logger.info(f"뉴스 매칭 사전 로드: {len(mapping)}개 종목")
        _loaded_at = now
    except Exception as e:
        logger.error(f"뉴스 매칭 사전 로드 실패: {e}")


def match_companies(text: str) -> list[dict]:
    """헤드라인에서 등장하는 상장 기업을 추출.

    반환: [{"ticker": "005930", "name": "삼성전자"}, ...] (중복 제거, 등장 순).
    """
    if not text:
        return []
    _ensure_loaded()
    if _pattern is None:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for m in _pattern.finditer(text):
        name = m.group(1)
        ticker = _name_to_ticker.get(name)
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append({"ticker": ticker, "name": name})
    return out
