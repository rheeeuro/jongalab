"""뉴스 재료 라우트 — 뉴스 속보 채널 언급 집계(news_mention)."""
from fastapi import APIRouter, Query

from core.repository import get_news_heat, get_today_news_by_stock

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/heat")
def get_news_heat_ranking(
    hours: int = Query(24, ge=1, le=168, description="집계 윈도우 (시간)"),
    limit: int = Query(20, ge=1, le=100, description="상위 종목 수"),
):
    """최근 N시간 뉴스 언급이 많은 종목 순위 (재료 히트맵/랭킹용)."""
    try:
        return {"success": True, "data": get_news_heat(hours=hours, limit=limit)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# 주의: "/heat" 보다 뒤에 등록해야 한다 (FastAPI 는 등록 순서대로 매칭).
@router.get("/{ticker}")
def get_today_news(
    ticker: str,
    limit: int = Query(15, ge=1, le=50, description="최대 헤드라인 수"),
):
    """특정 종목의 오늘 뉴스 헤드라인 목록 (최신순, 종목 상세 페이지용)."""
    try:
        return {"success": True, "data": get_today_news_by_stock(ticker, limit=limit)}
    except Exception as e:
        return {"success": False, "error": str(e)}
