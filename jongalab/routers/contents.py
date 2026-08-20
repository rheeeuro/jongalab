"""콘텐츠 분석 라우트"""
from typing import Optional
from fastapi import APIRouter, Query

from core.repository import get_contents_paginated, get_content_mention_summary, get_mention_stats

router = APIRouter(prefix="/api", tags=["contents"])


@router.get("/contents")
def get_contents(
    page: int = Query(1, description="현재 페이지 번호"),
    limit: int = Query(12, description="페이지 당 항목 수"),
    ticker: Optional[str] = Query(None, description="이 종목을 언급한 콘텐츠만"),
):
    """콘텐츠 분석 목록 (뉴스 탭 · 종목 상세 공용, 최근 7일).

    `ticker` 를 주면 그 종목 언급분만. 종목별 전량 조회는 두지 않는다 — 언급이 많은 대형주에서
    화면이 카드 100장 이상을 한 번에 받는다(그게 종목 상세가 무거웠던 원인이다).
    """
    try:
        result = get_contents_paginated(page, limit, ticker=ticker)
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/contents/mention-summary")
def get_contents_mention_summary(
    ticker: str = Query(..., description="종목코드"),
    days: int = Query(7, ge=1, le=30, description="집계 윈도우 (일)"),
):
    """종목 여론 요약 — 건수·채널 수·플랫폼·평균 감성·방향 분포 (종목 상세 요약 줄용)."""
    try:
        return {"success": True, "data": get_content_mention_summary(ticker, days=days)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/contents/mention-stats")
def get_contents_mention_stats(
    hours: int = Query(24, ge=1, le=168, description="집계 윈도우 (시간)"),
):
    """최근 N시간 콘텐츠 분석에서 언급된 섹터/기업 통계 (트리맵용).
    sector=None인 ticker는 통계에서 제외.
    """
    try:
        return {"success": True, "data": get_mention_stats(hours=hours)}
    except Exception as e:
        return {"success": False, "error": str(e)}


