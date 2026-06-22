"""
시장 데이터 서비스
- 개별 종목(시세/차트/종목명/주도주): 키움 REST API (6자리 종목코드 기준)
- 주요 지수(미국지수·국내지수·원자재·환율): yfinance
"""
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import yfinance as yf
from pykrx import stock as pykrx_stock

from core.repository.ticker import lookup_name_by_ticker


# ── 키움 데이터 서버 클라이언트 (국내 종목 시세 — lazy singleton, HTTP) ──
_kiwoom_api = None


def _get_kiwoom():
    """국내 종목 조회용 키움 HTTP 클라이언트 (lazy init). 토큰은 서버가 보장."""
    global _kiwoom_api
    if _kiwoom_api is None:
        from core.kiwoom_client import KiwoomRestClient
        _kiwoom_api = KiwoomRestClient()
    return _kiwoom_api


# ── 한국투자증권(KIS) 클라이언트 (코스피200 야간선물 시세 — lazy singleton) ──
_kis_api = None


def _get_kis():
    """선물 시세 조회용 KIS 클라이언트 (lazy init). 토큰은 클라이언트가 보장."""
    global _kis_api
    if _kis_api is None:
        from core.kis_client import KisRestClient
        _kis_api = KisRestClient()
    return _kis_api


def _kospi200_night_future() -> dict:
    """코스피200 야간선물 현재가.

    야간 WS 워커(kis_night_futures_ws)가 kis_night_future 단일행을 갱신한다.
    야간세션 중엔 실시간 체결가, 세션 종료 후엔 '마지막 야간 종가'를 다음
    세션까지 그대로 유지한다(주간선물 종가로 갈아타지 않는다 — 주간 시세는
    _kospi200_day_future 가 별도 카드로 제공).
    """
    base = {"symbol": "K200NF", "name": "코스피200 야간선물"}
    none = {**base, "price": None, "change": None, "change_percent": None}
    try:
        from core.repository.kis_night_future import get_night_future
        row = get_night_future()
    except Exception:
        return none
    if not row or row.get("price") is None:
        return none
    return {
        **base,
        "price": float(row["price"]),
        "change": float(row["change_val"]) if row.get("change_val") is not None else None,
        "change_percent": float(row["change_percent"]) if row.get("change_percent") is not None else None,
    }


def _kospi200_day_future() -> dict:
    """코스피200 주간선물 현재가 (KIS REST). 주간장 중엔 실시간, 장외엔 직전 종가."""
    base = {"symbol": "K200DF", "name": "코스피200 주간선물"}
    none = {**base, "price": None, "change": None, "change_percent": None}
    try:
        from core.kis_client import kospi200_front_month_code
        q = _get_kis().inquire_futures_price(kospi200_front_month_code())
    except Exception:
        return none
    if not q or q.get("price") is None:
        return none
    return {**base, **q}


def _parse_num(val) -> float:
    """키움 응답 가격 문자열("+53,500", "-1200") → float. 빈값/이상치는 0."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("+", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _norm_code(ticker: str) -> str:
    """'005930.KS', '005930_NX' 등 잔여 접미사가 있어도 6자리 코드만 추출"""
    return (ticker or "").split(".")[0].split("_")[0].strip()


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
    # 종가베팅 전 '내일 한국장 갭' 참고 지표.
    # 나스닥100 선물(NQ=F)은 yfinance, 코스피200 야간선물은 KIS REST(아래 병합)에서 조회한다.
    "FUTURES": [
        {"symbol": "NQ=F", "name": "나스닥100 선물"},
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


def _kiwoom_quote(code: str) -> dict:
    """키움 ka10001 기준 실시간 현재가/등락 (실패 시 None)"""
    none = {"price": None, "change": None, "change_percent": None}
    try:
        info = _get_kiwoom().get_stock_basic_info(code)
    except Exception:
        return none
    cur = abs(_parse_num(info.get("cur_prc")))
    if cur == 0:
        return none
    pct = _parse_num(info.get("flu_rt"))
    chg = _parse_num(info.get("pred_pre"))
    # flu_rt가 비어있으면 전일대비(pred_pre)로 등락률 산출
    if pct == 0 and chg != 0:
        prev = cur - chg
        if prev:
            pct = chg / prev * 100
    return {
        "price": cur,
        "change": round(chg, 2),
        "change_percent": round(pct, 2),
    }


def _kiwoom_price_on_date(code: str, ticker: str, date: str) -> dict:
    """키움 ka10081 일봉으로 특정 일자 종가 + 전 거래일 대비 등락률 조회"""
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "잘못된 날짜 형식입니다."}

    try:
        data = _get_kiwoom().get_daily_chart(code, dt=target.strftime("%Y%m%d"))
        candles = data.get("stk_dt_pole_chart_qry", [])
    except Exception:
        return {"error": "데이터를 찾을 수 없습니다."}

    tgt = target.strftime("%Y%m%d")
    rows = sorted(
        [c for c in candles if c.get("dt") and c["dt"] <= tgt],
        key=lambda c: c["dt"], reverse=True,
    )
    if not rows:
        return {"error": "데이터를 찾을 수 없습니다."}

    close = abs(_parse_num(rows[0].get("cur_prc")))
    if close == 0:
        return {"error": "데이터를 찾을 수 없습니다."}

    if len(rows) >= 2:
        prev = abs(_parse_num(rows[1].get("cur_prc")))
        change = round(close - prev, 2) if prev else 0.0
        change_percent = round(change / prev * 100, 2) if prev else 0.0
    else:
        change = 0.0
        change_percent = 0.0

    return {
        "ticker": ticker,
        "price": close,
        "change": change,
        "change_percent": change_percent,
    }


def fetch_stock_price(ticker: str, date: str | None = None) -> dict:
    """개별 종목 주가 및 등락률 조회 (키움 REST API).

    date 미지정 시 실시간 가격, 지정 시 해당 일자 종가와 전 거래일 대비 등락률.
    """
    code = _norm_code(ticker)
    if not code:
        return {"error": "데이터를 찾을 수 없습니다."}

    if date:
        return _kiwoom_price_on_date(code, ticker, date)

    q = _kiwoom_quote(code)
    if q["price"] is None:
        return {"error": "데이터를 찾을 수 없습니다."}
    return {"ticker": ticker, **q}


def fetch_stock_history(ticker: str, period: str = "7d") -> list[dict]:
    """최근 주가 히스토리 (차트 오버레이용, 키움 일봉)"""
    code = _norm_code(ticker)
    if not code:
        return []
    count = int(re.sub(r"\D", "", period) or "7")

    try:
        data = _get_kiwoom().get_daily_chart(code)
        candles = data.get("stk_dt_pole_chart_qry", [])
    except Exception:
        return []

    rows = sorted(
        [c for c in candles if c.get("dt")],
        key=lambda c: c["dt"], reverse=True,
    )[:count]

    result = []
    for c in reversed(rows):
        dt = c["dt"]
        result.append({
            "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
            "price": abs(_parse_num(c.get("cur_prc"))),
        })
    return result


def fetch_stock_name(ticker: str) -> str:
    """티커로 종목명 조회 (dictionary → pykrx → 키움 순서, 국장 전용)"""
    original_ticker = ticker
    ticker = (ticker or "").strip().upper()

    # 1) ticker_dictionary에서 우선 조회
    dict_name = lookup_name_by_ticker(ticker)
    if dict_name:
        return dict_name

    code = _norm_code(ticker)
    if not re.match(r"^\d{6}$", code):
        return original_ticker

    # 2) pykrx로 한글명 조회
    try:
        kr_name = pykrx_stock.get_market_ticker_name(code)
        if kr_name:
            return kr_name
    except Exception:
        pass

    # 3) 키움 ka10001 폴백
    try:
        info = _get_kiwoom().get_stock_basic_info(code)
        name = (info.get("stk_nm") or "").strip()
        if name:
            return name
    except Exception:
        pass

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

    # 코스피200 야간선물(마지막 야간 종가 유지) + 주간선물(실시간 REST)을
    # 선물 섹션 맨 앞에 합류 — 국장 시초가에 가장 직접적.
    grouped["FUTURES"] = [
        _kospi200_night_future(),
        _kospi200_day_future(),
    ] + grouped.get("FUTURES", [])

    return grouped
