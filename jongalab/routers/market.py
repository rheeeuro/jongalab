"""시장 데이터 라우트 (주가, 지수, 주도주, 거시 이벤트)"""
import re

from fastapi import APIRouter, HTTPException

from core.repository import get_youtube_sources
from core.repository import macro_event
from core.market_calendar import holidays_in_month
from core.market_data import (
    fetch_stock_price,
    fetch_stock_history,
    fetch_stock_name,
    fetch_market_indices,
    fetch_index_ohlc,
    resolve_index_name,
)

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/stock-price/{ticker}")
def get_stock_price(ticker: str, date: str | None = None):
    """키움 REST API로 주가 및 등락률 조회 (date 지정 시 해당일 종가 기준)"""
    try:
        return fetch_stock_price(ticker, date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-name/{ticker}")
def get_stock_name(ticker: str):
    """티커로 종목명을 조회"""
    return {"name": fetch_stock_name(ticker)}


@router.get("/stock-history/{ticker}")
def get_stock_history(ticker: str):
    """최근 7일 주가 데이터 가져오기 (차트 오버레이용)"""
    try:
        return fetch_stock_history(ticker)
    except Exception as e:
        return []


@router.get("/market-indices")
def get_market_indices():
    """주요 시장 지수 일괄 조회"""
    return fetch_market_indices()


@router.get("/market-index-history/{symbol}")
def get_market_index_history(symbol: str, range: str = "6m"):
    """시장 지수/심볼의 OHLCV 캔들 시계열 (상세 페이지 차트용, yfinance).

    range: 1m·3m·6m·1y. 커스텀 선물 심볼은 candles=[] (yfinance 미제공).
    """
    period = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y"}.get(range, "6mo")
    candles = fetch_index_ohlc(symbol, period=period)
    return {"symbol": symbol, "name": resolve_index_name(symbol), "candles": candles}


@router.get("/macro-events")
def get_macro_events(days: int = 30, month: str | None = None):
    """거시 이벤트(macro_event 캘린더 — FOMC·CPI·고용·PPI·금통위, 수동 시드).

    기본: 지금부터 days일 안(마켓 카드·메인 배너). month=YYYY-MM 이면 그 달 전체
    (과거 포함 — 리포트 캘린더 마커). severity 3 은 trading 거시 게이트의 시드 감액
    대상, 2 는 관찰 전용. 조회 실패는 빈 목록(대시보드는 이벤트 없이도 동작해야 한다).
    """
    try:
        if month and re.fullmatch(r"\d{4}-\d{2}", month):
            rows = macro_event.by_month(month)
        else:
            rows = macro_event.upcoming(min(max(days, 1), 120))
        return {"events": [{
            "date": r["event_time"].strftime("%Y-%m-%d"),
            "time": r["event_time"].strftime("%H:%M"),
            "name": r["name"], "category": r["category"],
            "severity": int(r["severity"]),
        } for r in rows]}
    except Exception:
        return {"events": []}


@router.get("/market-holidays")
def get_market_holidays(month: str):
    """month=YYYY-MM 의 KRX 휴장 평일(공휴일·대체공휴일·근로자의날·연말휴장 등)을
    이름과 함께 반환 — 리포트 캘린더의 휴일 라벨용. 조회 실패는 빈 목록."""
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise HTTPException(status_code=400, detail="month(YYYY-MM) 형식이 필요합니다.")
    try:
        return {"holidays": holidays_in_month(month)}
    except Exception:
        return {"holidays": []}


@router.get("/channels")
def get_channels():
    """모니터링 중인 채널 목록"""
    return get_youtube_sources()
