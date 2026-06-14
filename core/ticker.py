import re
import logging
import warnings
from ddgs import DDGS
from pykrx import stock as pykrx_stock

from core.repository import lookup_ticker, save_ticker

warnings.filterwarnings("ignore")


def _is_valid_kr_code(code: str) -> bool:
    """pykrx로 6자리 코드가 실제 상장 종목인지 검증 (코스피/코스닥 공통)"""
    try:
        return bool(pykrx_stock.get_market_ticker_name(code))
    except Exception:
        return False


def _search_ticker_online(company_name):
    """DuckDuckGo 검색으로 6자리 종목코드 추출 → pykrx 검증 (국장 전용)"""
    with DDGS() as ddgs:
        query = f"{company_name} 코스피 코스닥 종목코드"

        try:
            results = list(ddgs.text(query, max_results=8))
            combined_text = " ".join([f"{res.get('title')} {res.get('body')} {res.get('href')}" for res in results]).upper()

            codes = re.findall(r'\b(\d{6})\b', combined_text)
            for code in list(dict.fromkeys(codes)):
                if _is_valid_kr_code(code):
                    return code

        except Exception:
            pass

    return "Not Found"


def _get_single_ticker(company_name):
    """dictionary 조회 → INACTIVE면 스킵 → 없으면 온라인 검색 → 결과를 dictionary에 PENDING으로 저장"""
    cached = lookup_ticker(company_name)
    if cached:
        if cached["status"] == "INACTIVE":
            logging.info(f"🚫 INACTIVE 티커 스킵: {company_name} → {cached['ticker_symbol']}")
            return None
        logging.info(f"📖 Dictionary 캐시 히트: {company_name} → {cached['ticker_symbol']}")
        return cached["ticker_symbol"]

    ticker = _search_ticker_online(company_name)

    if ticker and ticker != "Not Found":
        save_ticker(company_name, ticker, status="PENDING")
        logging.info(f"📝 Dictionary에 새 티커 저장 (임시): {company_name} → {ticker}")

    return ticker


def get_tickers(names: list[str]) -> list[dict]:
    """
    names: 한글 또는 영문 기업명 리스트
    반환: [{"ticker": "005930", "name": "삼성전자"}, ...] 형식 (국장 전용, 6자리 코드)
    """
    tickers = []
    if not names:
        return tickers

    seen = set()
    for name in names:
        ticker = _get_single_ticker(name)
        if ticker and ticker != "Not Found" and ticker not in seen:
            seen.add(ticker)
            tickers.append({"ticker": ticker, "name": name})

    return tickers
