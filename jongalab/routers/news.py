"""뉴스 재료 라우트 — 뉴스 속보 채널 언급 집계(news_mention)."""
from fastapi import APIRouter, Query

from core.repository import get_news_heat

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
