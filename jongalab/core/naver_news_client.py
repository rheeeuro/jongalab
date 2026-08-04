"""네이버 증권 뉴스 클라이언트 — 경로가 둘이다(종목별 JSON / 섹션 목록 HTML).

  fetch_stock_news(code)             → 종목코드로 그 종목 기사 (집계 계층, source='naver')
  fetch_section_news(date_str, page) → 증권 섹션 전체 기사   (표시 계층, sec_news 테이블)

**같은 반환 계약**을 쓰지만 쓰임이 다르다. 종목별은 종목코드 조회라 귀속이 정확해서
재료 라벨·rule 의 원자료가 되고, 섹션 목록은 종목 귀속이 없는 대신 **모집단이 이미 증권
기사**라 뉴스 탭 화면 소스가 된다. 둘 중 하나로 합치려 하지 말 것 — 아래 각 절 참고.

[왜 종목별 경로인가]
유니버스 종목의 재료 라벨 커버리지가 47%(2026-07-31 실측 18/38)뿐이다. 나머지 53%는
텔레그램 뉴스 채널이 그 종목 기사를 안 옮겨서 생긴 공백이고, 채널을 늘려도 메워지지
않는다 — no_match 코퍼스 45건을 육안 분류해보니 55%의 실패분 중 상장사에 귀속 가능한
건 9%뿐이었고 나머지는 해외·정치·연예·거시라 애초에 종목 뉴스가 아니었다.
네이버 종목별 뉴스는 **종목코드로 조회하므로 사명 매칭이 아예 없다** — 그 공백에
정확히 맞는다(실측 커버리지 92% = 35/38, 신규 확보 17종목).

[계약 고정] 두 함수 모두 → [{headline, source_url, channel_name, published_at}]
이 반환 계약만 지키면 소스를 갈아끼울 수 있다(공식 검색 OpenAPI 등). 호출부(워커)는
네이버 응답 스키마를 모른다.

[엔드포인트 ①] GET {BASE}/api/news/stock/{code}?pageSize=&page=1 → JSON
  응답은 '기사 묶음' 배열이고 각 묶음의 items 가 실제 기사다(관련기사 그룹). 평탄화해서 쓴다.
  item: officeId/articleId(안정 URL 키) · officeName(언론사) · datetime(YYYYMMDDHHMM) ·
        titleFull(전체 제목 — title 은 목록용으로 잘려 온다) · body(발췌, 현재 미사용)

[왜 섹션 목록 경로가 따로 필요한가]
뉴스 탭 헤드라인이 텔레그램 종합 속보 채널을 읽는 동안, 주식과 무관한 기사가 화면에
올라왔다 — 2026-08-05 실측 14일 5,674기사 중 4.1%가 명백한 오탐이다(일반명사 사명
`70대 남성 사망`→남성 004270 · KBO 구단명 `한화, 삼성 4-1 제압`→한화 000880).
매처를 고쳐도 못 막는다. **모집단이 종합 뉴스**인 게 원인이라 모집단을 바꾼다.
종목별 경로로는 대체가 안 된다 — 그쪽은 유니버스 62종목만 보므로 시황·환율·정책처럼
종목이 안 붙는 증권 기사가 통째로 빠진다.

[엔드포인트 ②] GET https://finance.naver.com/news/news_list.naver
                   ?mode=LSS2D&section_id=101&section_id2=258&date=YYYYMMDD&page=N → HTML
  `section_id2=258`(증권) 전체 목록. 하위 섹션(401 시황·전망 / 402 기업·종목분석 /
  403 해외증시 / 404 채권·선물 / 405 공시·메모 / 406 환율)의 합집합 + 미분류분이라
  섹션별로 나눠 긁을 이유가 없다. 실측 2026-08-04 = 56페이지 × 20건 ≈ 1,120건/일
  (텔레그램 465건/일의 2.4배).
  ⚠️ **JSON API 가 아니라 EUC-KR HTML 이다.** 마크업이 바뀌면 파서가 조용히 0건을
  돌려주므로 호출부가 '0건'을 정상으로 취급하지 않게 했다(sec_news_collector 참고).
  제목은 `<a title="...">` **속성**에서 뽑는다 — 링크 안쪽 텍스트는 목록용으로 잘려 온다.

[레이트리밋] 공개 API 키가 없는 대신 UA 헤더를 요구한다. 실측 종목별 38종목 14초 /
평균 응답 0.08s / HTTP 200 전건. 섹션 목록은 30분 주기로 앞 몇 페이지만 보므로
하루 100콜 미만이다. 403·429 는 차단 신호로 따로 구분해 호출부가 사이클을 조기 종료한다.
"""
import html
import logging
import re
from datetime import datetime

import requests

from core.config import (
    NAVER_NEWS_BASE_URL, NAVER_NEWS_PAGE_SIZE, NAVER_NEWS_TIMEOUT,
)

logger = logging.getLogger("NaverNewsClient")

SOURCE = "naver"

# 증권 섹션 목록 — 종목별 JSON 과 호스트가 다르다(m.stock 은 모바일 API, finance 는 웹 목록).
SECTION_LIST_URL = "https://finance.naver.com/news/news_list.naver"
SECTION_PARAMS = {"mode": "LSS2D", "section_id": "101", "section_id2": "258"}
# 목록 HTML 은 EUC-KR 이다. requests 는 헤더를 보고 ISO-8859-1 로 잘못 잡으므로 직접 지정한다.
_SECTION_ENCODING = "euc-kr"

# 브라우저 UA 가 없으면 응답이 달라진다(공개 API 키가 없는 대신의 요구사항).
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 기사 원문 뷰어 — officeId/articleId 조합이 안정적이라 (source_url, ticker) UNIQUE 멱등키가 된다.
ARTICLE_URL = "https://n.news.naver.com/mnews/article/{office_id}/{article_id}"

# 제목에 HTML 엔티티가 그대로 섞여 온다(&quot;·&hellip;·&middot;·&uarr; 등). 헤드라인은
# LLM 프롬프트·화면에 그대로 들어가므로 여기서 한 번만 걷어낸다. 손수 만든 치환표 대신
# html.unescape 를 쓰는 이유: 목록 HTML 은 종목별 JSON 보다 엔티티 종류가 훨씬 많아
# 표를 유지하는 쪽이 반드시 뒤처진다(빠진 엔티티는 화면에 &hellip; 로 샌다).
_WS_RE = re.compile(r"\s+")

_HEADLINE_MAX = 500      # headline 컬럼 한도 (실측 최대 46자 — 여유 충분)
_URL_MAX = 500           # source_url 컬럼 한도 (실측 최대 53자)


class NaverNewsError(RuntimeError):
    """조회 실패(네트워크·형식 오류). 호출부가 잡아 다음 주기에 재시도한다."""


class NaverNewsBlocked(NaverNewsError):
    """403/429 — 차단·레이트리밋 신호. 호출부는 남은 종목을 포기하고 사이클을 끝낸다."""


def _clean_title(raw: str) -> str:
    return _WS_RE.sub(" ", html.unescape(raw or "")).strip()


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


# ── 증권 섹션 목록 (표시 계층) ─────────────────────────────────────────────
# 기사 1건 = 제목 앵커(class="articleSubject") + 바로 뒤 메타(span.press / span.wdate).
# **제목 앵커 위치로 잘라서** 각 조각 안에서 메타를 찾는다. 이유 두 가지:
#   · <dl> 은 기사 단위가 아니다 — 실측 20건이 <dl> 2개에 뭉쳐 들어온다. 감싸는 태그도
#     썸네일 유무에 따라 dt/dd 로 바뀌므로 컨테이너를 기준으로 삼을 수 없다.
#   · 문서 전체에서 제목·메타를 따로 findall 해 zip 하면 한쪽이 하나만 빠져도 이후 전건이
#     밀려 **엉뚱한 언론사·시각이 붙는다**(조용한 오염이라 파싱 실패보다 나쁘다).
_SUBJECT_RE = re.compile(
    r'articleSubject"\s*>\s*<a\s+href="([^"]+)"\s+title="([^"]*)"', re.S
)
_PRESS_RE = re.compile(r'<span class="press">([^<]*)</span>')
_WDATE_RE = re.compile(r'<span class="wdate">([^<]*)</span>')
_OFFICE_ID_RE = re.compile(r"office_id=(\d+)")
_ARTICLE_ID_RE = re.compile(r"article_id=(\d+)")


def _parse_section_block(subject: re.Match, block: str) -> dict | None:
    """제목 앵커 + 그 뒤 조각 → 반환 계약 형태. 필수 조각이 빠지면 None(그 기사만 버린다)."""
    wdate = _WDATE_RE.search(block)
    if not wdate:
        return None
    href, title = subject.group(1), subject.group(2)
    office = _OFFICE_ID_RE.search(href)
    article = _ARTICLE_ID_RE.search(href)
    headline = _clean_title(title)
    if not (office and article and headline):
        return None
    try:
        published_at = datetime.strptime(wdate.group(1).strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    press = _PRESS_RE.search(block)
    return {
        "headline": headline[:_HEADLINE_MAX],
        "source_url": ARTICLE_URL.format(
            office_id=office.group(1), article_id=article.group(1)
        )[:_URL_MAX],
        "channel_name": (_clean_title(press.group(1))[:100] if press else None) or None,
        "published_at": published_at,
    }


def fetch_section_news(date_str: str, page: int = 1) -> list[dict]:
    """증권 섹션 목록 1페이지(최신순 20건). 날짜 필터는 URL 파라미터가 이미 해 준다.

    date_str: 'YYYY-MM-DD'. 반환: [{headline, source_url, channel_name, published_at}].
    빈 목록은 **정상**이다 — 그 날짜의 마지막 페이지를 넘어섰다는 뜻이고, 호출부가
    페이지 순회를 멈추는 신호로 쓴다(파서 파손과의 구분은 호출부 책임 — 모듈 주석 참고).
    """
    params = {**SECTION_PARAMS, "date": date_str.replace("-", ""), "page": int(page)}
    try:
        resp = requests.get(SECTION_LIST_URL, params=params,
                            headers={"User-Agent": _UA}, timeout=NAVER_NEWS_TIMEOUT)
    except requests.RequestException as e:
        raise NaverNewsError(f"섹션 목록 p{page} 요청 실패: {e}") from e

    if resp.status_code in (403, 429):
        raise NaverNewsBlocked(f"섹션 목록 p{page} 차단 응답 status={resp.status_code}")
    if resp.status_code != 200:
        raise NaverNewsError(f"섹션 목록 p{page} 비정상 응답 status={resp.status_code}")

    resp.encoding = _SECTION_ENCODING
    body = resp.text
    subjects = list(_SUBJECT_RE.finditer(body))
    out: list[dict] = []
    for i, subject in enumerate(subjects):
        # 이 기사의 메타는 다음 제목 앵커 전까지에 있다(마지막 건은 문서 끝까지).
        end = subjects[i + 1].start() if i + 1 < len(subjects) else len(body)
        parsed = _parse_section_block(subject, body[subject.end():end])
        if parsed:
            out.append(parsed)
    return out
