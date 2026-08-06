"""콘텐츠 분석의 기업명 → 국내 종목코드 해석 (ticker_dictionary ACTIVE 전용).

해석 근거는 `ticker_dictionary` 의 **ACTIVE 행뿐**이다. `news_ticker_seed` 워커가 키움
ka10099 로 코스피/코스닥 전 종목을 ACTIVE 로 채우고, 흔히 쓰는 별칭(`LG엔솔`·`네이버`·
`삼성바이오`)은 관리자가 사전에서 ACTIVE 로 승인해 늘린다.

사전에 없는 이름(해외기업·비상장·제품명·업종어)은 **국장 종목코드가 없으므로 해석하지 않고
버린다**. 버려진 이름만 있는 콘텐츠는 호출부의 `should_save_content(allow_no_ticker=False)`
에서 저장 자체가 스킵된다.

이름 매칭은 공백·기호를 무시하는 정규화 비교까지만 한다(`한미 반도체` → `한미반도체`).
그 이상의 추측(웹 검색·부분일치)은 하지 않는다 — 콘텐츠 티커는 종합점수 가점
(`CONTENT_SCORE_MAX`)으로 이어져, 틀린 코드가 그대로 잘못된 매수 후보가 된다.
"""
import logging
import re
import time

from core.repository.ticker import get_ticker_dictionary

# 사전 갱신 주기(초). 시딩 워커·관리자 승인분이 다음 갱신에 반영된다(news_matcher 와 동일 방식).
REFRESH_SECONDS = 3600

# 공백·기호·대소문자 차이만 흡수한다(`HD 현대 일렉트릭` → `HD현대일렉트릭`).
_NON_NAME_RE = re.compile(r"[^0-9A-Z가-힣]")

_index: dict[str, str] = {}   # 정규화 기업명 → 종목코드
_loaded_at: float = 0.0


def _norm(name: str | None) -> str:
    return _NON_NAME_RE.sub("", (name or "").upper())


def _ensure_loaded(force: bool = False) -> None:
    """ACTIVE 사전을 인메모리 인덱스로 로드 (TTL 갱신).

    로드 실패·빈 응답이면 **직전 인덱스를 유지**한다 — 일시적 DB 오류로 사전이 비면
    모든 콘텐츠가 '티커 없음'으로 스킵되기 때문이다.
    """
    global _index, _loaded_at
    now = time.time()
    if not force and _index and (now - _loaded_at) < REFRESH_SECONDS:
        return

    try:
        entries = get_ticker_dictionary(status="ACTIVE")
    except Exception as e:
        logging.error(f"티커 사전 로드 실패 (직전 인덱스 유지): {e}")
        return

    index: dict[str, str] = {}
    for row in entries:
        key = _norm(row.get("company_name"))
        code = (row.get("ticker_symbol") or "").strip()
        if key and code:
            index.setdefault(key, code)

    if not index:
        logging.warning("ACTIVE 티커 사전이 비어있음 — news_ticker_seed 워커 확인 필요")
        return

    _index, _loaded_at = index, now
    logging.info(f"📖 티커 사전 로드: {len(index)}개 종목")


def get_tickers(names: list[str]) -> list[dict]:
    """기업명 리스트 → `[{"ticker": "005930", "name": "삼성전자"}, ...]` (국장 6자리 코드).

    사전에 없는 이름은 조용히 제외되므로, 결과가 빈 리스트일 수 있다.
    `name` 은 **입력받은 이름 그대로** 돌려준다 — `save_content_analysis` 가 이 name 으로
    `stocks[].name` 에 티커를 붙이기 때문에 정식명으로 바꾸면 그 연결이 끊긴다.
    """
    if not names:
        return []

    _ensure_loaded()

    tickers: list[dict] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for name in names:
        code = _index.get(_norm(name))
        if not code:
            dropped.append(name)
            continue
        if code in seen:
            continue
        seen.add(code)
        tickers.append({"ticker": code, "name": name})

    if dropped:
        logging.info(f"🚫 국장 사전 미등재로 제외: {', '.join(dropped)}")

    return tickers
