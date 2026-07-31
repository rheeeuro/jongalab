"""네이버 증권 종목별 뉴스 클라이언트 — 종목코드로 당일 기사 목록을 받는 최소 래퍼.

[왜 이 소스인가]
유니버스 종목의 재료 라벨 커버리지가 47%(2026-07-31 실측 18/38)뿐이다. 나머지 53%는
텔레그램 뉴스 채널이 그 종목 기사를 안 옮겨서 생긴 공백이고, 채널을 늘려도 메워지지
않는다 — no_match 코퍼스 45건을 육안 분류해보니 55%의 실패분 중 상장사에 귀속 가능한
건 9%뿐이었고 나머지는 해외·정치·연예·거시라 애초에 종목 뉴스가 아니었다.
네이버 종목별 뉴스는 **종목코드로 조회하므로 사명 매칭이 아예 없다** — 그 공백에
정확히 맞는다(실측 커버리지 92% = 35/38, 신규 확보 17종목).

[계약 고정] fetch_stock_news(code) → [{headline, source_url, channel_name, published_at}]
이 반환 계약만 지키면 소스를 갈아끼울 수 있다(공식 검색 OpenAPI 등). 호출부(워커)는
네이버 응답 스키마를 모른다.

[엔드포인트] GET {BASE}/api/news/stock/{code}?pageSize=&page=1 → JSON
  응답은 '기사 묶음' 배열이고 각 묶음의 items 가 실제 기사다(관련기사 그룹). 평탄화해서 쓴다.
  item: officeId/articleId(안정 URL 키) · officeName(언론사) · datetime(YYYYMMDDHHMM) ·
        titleFull(전체 제목 — title 은 목록용으로 잘려 온다) · body(발췌, 현재 미사용)

[레이트리밋] 공개 API 키가 없는 대신 UA 헤더를 요구한다. 실측 38종목 14초 / 평균 응답
0.08s / HTTP 200 전건. 유니버스 한정 폴링이라 하루 ~900콜 수준.
403·429 는 차단 신호로 따로 구분해 호출부가 사이클을 조기 종료한다.
"""
import logging
import re
from datetime import datetime

import requests

from core.config import (
    NAVER_NEWS_BASE_URL, NAVER_NEWS_PAGE_SIZE, NAVER_NEWS_TIMEOUT,
)

logger = logging.getLogger("NaverNewsClient")

SOURCE = "naver"

# 브라우저 UA 가 없으면 응답이 달라진다(공개 API 키가 없는 대신의 요구사항).
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 기사 원문 뷰어 — officeId/articleId 조합이 안정적이라 (source_url, ticker) UNIQUE 멱등키가 된다.
ARTICLE_URL = "https://n.news.naver.com/mnews/article/{office_id}/{article_id}"

# 제목에 HTML 엔티티가 그대로 섞여 온다(&quot; 등). 헤드라인은 LLM 프롬프트·화면에 그대로
# 들어가므로 여기서 한 번만 걷어낸다.
_ENTITIES = {"&quot;": '"', "&apos;": "'", "&lt;": "<", "&gt;": ">", "&amp;": "&",
             "&nbsp;": " ", "&#039;": "'"}
_WS_RE = re.compile(r"\s+")

_HEADLINE_MAX = 500      # news_mention.headline 컬럼 한도 (실측 최대 46자 — 여유 충분)
_URL_MAX = 500           # news_mention.source_url 컬럼 한도 (실측 최대 53자)


class NaverNewsError(RuntimeError):
    """조회 실패(네트워크·형식 오류). 호출부가 잡아 다음 주기에 재시도한다."""


class NaverNewsBlocked(NaverNewsError):
    """403/429 — 차단·레이트리밋 신호. 호출부는 남은 종목을 포기하고 사이클을 끝낸다."""


def _clean_title(raw: str) -> str:
    text = raw or ""
    for ent, ch in _ENTITIES.items():
        text = text.replace(ent, ch)
    return _WS_RE.sub(" ", text).strip()


def _parse_item(item: dict) -> dict | None:
    """네이버 item → 반환 계약 형태. 필수 필드가 빠지면 None(그 기사만 버린다)."""
    office_id = str(item.get("officeId") or "").strip()
    article_id = str(item.get("articleId") or "").strip()
    stamp = str(item.get("datetime") or "").strip()
    headline = _clean_title(item.get("titleFull") or item.get("title") or "")
    if not (office_id and article_id and headline) or len(stamp) != 12:
        return None
    try:
        published_at = datetime.strptime(stamp, "%Y%m%d%H%M")
    except ValueError:
        return None
    return {
        "headline": headline[:_HEADLINE_MAX],
        "source_url": ARTICLE_URL.format(office_id=office_id, article_id=article_id)[:_URL_MAX],
        "channel_name": (item.get("officeName") or "")[:100] or None,
        "published_at": published_at,
    }


def fetch_stock_news(code: str, page_size: int | None = None) -> list[dict]:
    """종목의 최근 기사 목록. 최신순 그대로 반환하고 날짜 필터는 호출부가 한다.

    반환: [{headline, source_url, channel_name, published_at}] — 파싱 불가 항목은 제외.
    """
    url = f"{NAVER_NEWS_BASE_URL}/api/news/stock/{code}"
    params = {"pageSize": int(page_size or NAVER_NEWS_PAGE_SIZE), "page": 1}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": _UA},
                            timeout=NAVER_NEWS_TIMEOUT)
    except requests.RequestException as e:
        raise NaverNewsError(f"{code} 요청 실패: {e}") from e

    if resp.status_code in (403, 429):
        raise NaverNewsBlocked(f"{code} 차단 응답 status={resp.status_code}")
    if resp.status_code != 200:
        raise NaverNewsError(f"{code} 비정상 응답 status={resp.status_code}")

    try:
        groups = resp.json()
    except ValueError as e:
        raise NaverNewsError(f"{code} JSON 파싱 실패: {e}") from e
    if not isinstance(groups, list):
        raise NaverNewsError(f"{code} 예상치 못한 응답 형식: {type(groups).__name__}")

    out: list[dict] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if isinstance(item, dict):
                parsed = _parse_item(item)
                if parsed:
                    out.append(parsed)
    return out
