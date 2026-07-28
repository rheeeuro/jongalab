"""DART 전자공시 OpenAPI 클라이언트 — 공시검색(list.json) 전용 최소 래퍼.

키움/KIS 클라이언트와 달리 토큰 발급이 없다(발급받은 API 키를 쿼리로 보낸다).
필요한 건 '오늘 접수된 상장사 공시 목록' 하나뿐이라 엔드포인트도 하나만 감싼다
(설계 5원칙 #3 — 필요해질 때 넓힌다).

[응답 status 코드]
  000 정상 / 013 조회 데이터 없음(정상적인 빈 결과) / 그 외는 오류 → DartError.
  013 을 오류로 취급하면 공시 없는 시간대마다 워커가 실패하므로 빈 목록으로 정규화한다.

[레이트리밋] DART 는 키당 일 20,000 콜. 수집기는 30분 주기 × 시장 2종 × 페이지 수라
하루 수백 콜 수준이라 여유가 크다.
"""
import logging

import requests

from core.config import DART_API_KEY, DART_BASE_URL

logger = logging.getLogger("DartClient")

# 유가증권(Y)·코스닥(K)만 — 코넥스/기타법인은 종가베팅 유니버스 밖이다.
MARKET_CLASSES: tuple[str, ...] = ("Y", "K")

_PAGE_COUNT = 100          # list.json 최대 페이지 크기
_MAX_PAGES = 30            # 폭주 방어 상한(하루 최대 3000건이면 충분)
_TIMEOUT = 10

_STATUS_EMPTY = "013"      # 조회된 데이터가 없습니다
_STATUS_OK = "000"

# 공시 원문 뷰어 — 접수번호로 바로 열린다
DOC_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


class DartError(RuntimeError):
    """DART API 오류(키 누락·인증 실패·서버 오류). 호출부가 잡아 다음 주기에 재시도한다."""


def is_configured() -> bool:
    """API 키가 주입돼 있는가 — 워커가 미설정 시 조용히 종료하는 데 쓴다."""
    return bool(DART_API_KEY)


def _fetch_page(bgn_de: str, end_de: str, corp_cls: str, page_no: int) -> dict:
    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "corp_cls": corp_cls,
        "page_no": page_no,
        "page_count": _PAGE_COUNT,
    }
    try:
        resp = requests.get(f"{DART_BASE_URL}/api/list.json", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise DartError(f"DART 요청 실패 (corp_cls={corp_cls}, page={page_no}): {e}") from e

    status = str(data.get("status") or "")
    if status == _STATUS_EMPTY:
        return {"list": [], "total_page": 0}
    if status != _STATUS_OK:
        raise DartError(f"DART 응답 오류 status={status} msg={data.get('message')}")
    return data


def capital_increase_methods(corp_code: str, date_yyyymmdd: str) -> dict[str, str]:
    """유상증자 결정 상세(piicDecsn)에서 **증자방식**을 접수번호별로 조회.

    보고서명('주요사항보고서(유상증자결정)')만으로는 주주배정(희석 악재)과 제3자배정
    (전략적 투자 유치 — 호재일 수 있음)을 구분할 수 없다. 2026-07-27 NAVER 가 NVIDIA
    대상 제3자배정 유상증자(1.48조, 희석 4.6%)를 내고 주가가 올랐는데, 제목 기반 분류는
    이를 악재로 보고 그날 1순위 종목을 제외할 뻔했다 — 그래서 이 조회를 붙인다.

    반환: {rcept_no: ic_mthn} — 예 {"20260727000001": "제3자배정증자"}.
    조회 실패·데이터 없음은 빈 dict(호출부가 '방식 미상'으로 보수 처리한다).
    """
    if not is_configured() or not corp_code:
        return {}
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": date_yyyymmdd,
        "end_de": date_yyyymmdd,
    }
    try:
        resp = requests.get(f"{DART_BASE_URL}/api/piicDecsn.json", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("유상증자 방식 조회 실패 (corp_code=%s): %s", corp_code, e)
        return {}
    if str(data.get("status") or "") != _STATUS_OK:
        return {}
    return {
        str(it.get("rcept_no") or ""): str(it.get("ic_mthn") or "")
        for it in (data.get("list") or [])
        if it.get("rcept_no")
    }


def list_filings(date_yyyymmdd: str) -> list[dict]:
    """하루치 유가·코스닥 공시 전체를 페이지 끝까지 수집.

    반환: DART 원본 항목 목록([{corp_name, stock_code, report_nm, rcept_no, rcept_dt, ...}]).
    stock_code 가 빈 항목(비상장 계열사 등)은 여기서 걸러낸다 — 종목에 붙일 수 없다.
    시장 하나가 실패하면 그 시장만 건너뛰고 나머지는 반환한다(부분 수집 허용).
    """
    if not is_configured():
        raise DartError("DART_API_KEY 미설정 — .env 에 키를 넣어주세요")

    out: list[dict] = []
    for corp_cls in MARKET_CLASSES:
        try:
            page_no = 1
            while page_no <= _MAX_PAGES:
                data = _fetch_page(date_yyyymmdd, date_yyyymmdd, corp_cls, page_no)
                items = data.get("list") or []
                out.extend(it for it in items if (it.get("stock_code") or "").strip())
                total_page = int(data.get("total_page") or 0)
                if page_no >= total_page:
                    break
                page_no += 1
            else:
                logger.warning("DART 페이지 상한(%d) 도달 — corp_cls=%s 잔여 누락 가능",
                               _MAX_PAGES, corp_cls)
        except DartError as e:
            logger.error("DART 수집 실패 (corp_cls=%s) — 이 시장 건너뜀: %s", corp_cls, e)
    return out
