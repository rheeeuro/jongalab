"""시장 데이터 라우트 (주가, 지수, 주도주)"""
from fastapi import APIRouter, HTTPException

from core.repository import get_youtube_sources
from core.market_data import (
    fetch_stock_price,
    fetch_stock_history,
    fetch_stock_name,
    fetch_market_indices,
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


@router.get("/channels")
def get_channels():
    """모니터링 중인 채널 목록"""
    return get_youtube_sources()
