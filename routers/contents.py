"""콘텐츠 분석 라우트"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.repository import get_contents_paginated, get_contents_by_ticker, get_mention_stats

router = APIRouter(prefix="/api", tags=["contents"])


class ContentAnalysis(BaseModel):
    id: int
    external_id: str
    source_name: str
    title: str
    analysis_content: str
    sentiment_score: Optional[int] = 50
    platform: str
    source_url: Optional[str] = None
    created_at: str


@router.get("/contents")
def get_contents(
    page: int = Query(1, description="현재 페이지 번호"),
    limit: int = Query(12, description="페이지 당 항목 수"),
    market: str = Query("ALL", description="시장 필터 (ALL, US, KR 등)"),
):
    try:
        result = get_contents_paginated(page, limit, market)
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/contents/mention-stats")
def get_contents_mention_stats(
    market: str = Query("ALL", description="시장 필터 (ALL, US, KR)"),
    hours: int = Query(12, ge=1, le=168, description="집계 윈도우 (시간)"),
):
    """최근 N시간 콘텐츠 분석에서 언급된 섹터/기업 통계 (트리맵용).
    sector=None인 ticker는 통계에서 제외.
    """
    try:
        return {"success": True, "data": get_mention_stats(market=market, hours=hours)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/contents/{ticker}", response_model=List[ContentAnalysis])
def get_ticker_contents(ticker: str):
    """특정 티커(종목)와 관련된 콘텐츠 조회"""
    try:
        return get_contents_by_ticker(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
