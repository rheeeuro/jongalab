"""
시장 데이터 서비스 — yfinance/pykrx 기반 주가·지수 조회
"""
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import yfinance as yf
from pykrx import stock as pykrx_stock

from core.repository.ticker import lookup_name_by_ticker


# ── 시장 지수 정의 ──

MARKET_INDICES = {
    "US": [
        {"symbol": "^GSPC", "name": "S&P 500"},
        {"symbol": "^IXIC", "name": "NASDAQ"},
        {"symbol": "^DJI", "name": "다우존스"},
        {"symbol": "^VIX", "name": "VIX (공포지수)"},
        {"symbol": "DX-Y.NYB", "name": "달러 인덱스"},
    ],
    "KR": [
        {"symbol": "^KS11", "name": "코스피"},
        {"symbol": "^KQ11", "name": "코스닥"},
        {"symbol": "USDKRW=X", "name": "원/달러 환율"},
    ],
    "COMMODITIES": [
        {"symbol": "GC=F", "name": "금"},
        {"symbol": "CL=F", "name": "WTI 원유"},
        {"symbol": "BTC-USD", "name": "비트코인"},
    ],
}

# ── 시장별 주도주 ──

MARKET_LEADERS = {
    "US": [
        {"symbol": "AAPL", "name": "Apple"},
        {"symbol": "NVDA", "name": "NVIDIA"},
        {"symbol": "MSFT", "name": "Microsoft"},
        {"symbol": "GOOGL", "name": "Alphabet"},
        {"symbol": "AMZN", "name": "Amazon"},
        {"symbol": "TSLA", "name": "Tesla"},
        {"symbol": "META", "name": "Meta"},
    ],
    "KR": [
        {"symbol": "005930.KS", "name": "삼성전자"},
        {"symbol": "000660.KS", "name": "SK하이닉스"},
        {"symbol": "373220.KS", "name": "LG에너지솔루션"},
        {"symbol": "207940.KS", "name": "삼성바이오로직스"},
        {"symbol": "005380.KS", "name": "현대자동차"},
        {"symbol": "000270.KS", "name": "기아"},
        {"symbol": "035420.KS", "name": "NAVER"},
    ],
}


def _safe_float(val) -> float | None:
    """nan/inf를 None으로 변환하여 JSON 직렬화 안전하게 처리"""
    if val is None:
        return None
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


def _fetch_quote(item: dict) -> dict:
    """하나의 종목/지수 데이터를 yfinance에서 조회"""
    empty = {**item, "price": None, "change": None, "change_percent": None}
    try:
        stock = yf.Ticker(item["symbol"])
        hist = stock.history(period="5d")
        if hist.empty:
            return empty
        current = _safe_float(hist["Close"].iloc[-1])
        if current is None:
            return empty
        prev = _safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        if prev is None or prev == 0:
            return {**item, "price": current, "change": None, "change_percent": None}
        change = round(current - prev, 2)
        change_pct = round((change / prev) * 100, 2)
        return {
            **item,
            "price": current,
            "change": change,
            "change_percent": change_pct,
        }
    except Exception:
        return empty


def fetch_stock_price(ticker: str, date: str | None = None) -> dict:
    """개별 종목 주가 및 등락률 조회.

    date 미지정 시 실시간 가격, 지정 시 해당 일자 종가와 전 거래일 대비 등락률.
    """
    stock = yf.Ticker(ticker)

    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": "잘못된 날짜 형식입니다."}
        # 휴장일을 고려해 2주치를 가져온 뒤 target까지 슬라이싱
        start = (target - timedelta(days=14)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = stock.history(start=start, end=end)
    else:
        hist = stock.history(period="2d")

    if hist.empty or len(hist) < 1:
        return {"error": "데이터를 찾을 수 없습니다."}

    current_price = _safe_float(hist['Close'].iloc[-1])
    if current_price is None:
        return {"error": "데이터를 찾을 수 없습니다."}

    if len(hist) >= 2:
        prev_close = _safe_float(hist['Close'].iloc[-2])
        if prev_close and prev_close != 0:
            change = round(current_price - prev_close, 2)
            change_percent = round((change / prev_close) * 100, 2)
        else:
            change = 0.0
            change_percent = 0.0
    else:
        change = 0.0
        change_percent = 0.0

    return {
        "ticker": ticker,
        "price": current_price,
        "change": change,
        "change_percent": change_percent,
    }


def fetch_stock_history(ticker: str, period: str = "7d") -> list[dict]:
    """최근 주가 히스토리 (차트 오버레이용)"""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)

    result = []
    if not hist.empty:
        for dt, row in hist.iterrows():
            result.append({
                "date": dt.strftime("%Y-%m-%d"),
                "price": round(row['Close'], 2),
            })
    return result


def fetch_stock_name(ticker: str) -> str:
    """티커로 종목명 조회 (dictionary → pykrx → yfinance 순서)"""
    original_ticker = ticker
    ticker = ticker.strip().upper()

    # 1) ticker_dictionary에서 우선 조회
    dict_name = lookup_name_by_ticker(ticker)
    if dict_name:
        return dict_name

    # 2) 한국 종목이면 pykrx로 한글명 조회
    m = re.match(r"^(\d{6})\.(KS|KQ)$", ticker)
    if m:
        code = m.group(1)
        try:
            kr_name = pykrx_stock.get_market_ticker_name(code)
            if kr_name:
                return kr_name
        except Exception:
            pass

    # 3) yfinance 폴백
    try:
        stock = yf.Ticker(ticker)
        info = stock.get_info()
        return (
            info.get("displayName")
            or info.get("shortName")
            or info.get("longName")
            or original_ticker
        )
    except Exception:
        return original_ticker


def fetch_market_indices() -> dict:
    """주요 시장 지수 일괄 조회 (카테고리별 그룹핑)"""
    all_items = []
    for items in MARKET_INDICES.values():
        all_items.extend(items)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_fetch_quote, all_items))

    grouped = {}
    idx = 0
    for category, items in MARKET_INDICES.items():
        grouped[category] = results[idx : idx + len(items)]
        idx += len(items)

    return grouped


def fetch_market_leaders(market: str) -> list[dict]:
    """시장별 주도주 조회"""
    leaders = MARKET_LEADERS.get(market, [])
    if not leaders:
        return []

    with ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(_fetch_quote, leaders))
