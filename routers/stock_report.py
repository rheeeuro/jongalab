"""종목일간리포트 라우트"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.repository import (
    get_stock_report,
    get_stock_report_history,
    get_stock_reports_by_date,
    get_stock_report_dates,
    get_sector_reports_by_date,
    get_content_by_stock_and_date,
    get_gap_stats_by_dates,
    get_top_themes_by_dates,
)

router = APIRouter(prefix="/api", tags=["stock-report"])


class SupplyHistoryItem(BaseModel):
    date: str = ""
    inst_net_buy: int = 0
    frgn_net_buy: int = 0
    indv_net_buy: int = 0


class HourlyCandleItem(BaseModel):
    time: str = ""
    open: int = 0
    high: int = 0
    low: int = 0
    close: int = 0
    volume: int = 0


class StockReport(BaseModel):
    id: int
    report_date: str
    stock_code: str
    stock_name: str
    sector: Optional[str] = None
    current_price: int = 0
    change_pct: float = 0.0
    trading_value: int = 0
    market_cap: int = 0
    supply_grade: str = "D"
    supply_score: float = 0.0
    inst_net_buy: int = 0
    frgn_net_buy: int = 0
    indv_net_buy: int = 0
    prog_net_buy: int = 0
    supply_days: int = 0
    supply_history: List[SupplyHistoryItem] = []
    ma_aligned: bool = False
    near_high: bool = False
    hourly_candles: List[HourlyCandleItem] = []
    is_leader: bool = False
    is_theme_stock: bool = False
    content_score: float = 0.0
    score: float = 0.0
    rank_no: int = 0
    gap_nxt_price: Optional[int] = None
    gap_nxt_pct: Optional[float] = None
    gap_krx_price: Optional[int] = None
    gap_krx_pct: Optional[float] = None
    gap_checked_at: Optional[str] = None
    created_at: Optional[str] = None


class ContentAnalysisItem(BaseModel):
    id: int
    title: str = ""
    analysis_content: str = ""
    sentiment_score: int = 50
    source_name: str = ""
    platform: str = ""
    source_url: Optional[str] = None
    created_at: Optional[str] = None


class StockReportDetail(BaseModel):
    report: StockReport
    content_analyses: List[ContentAnalysisItem] = []


class SectorStock(BaseModel):
    stk_cd: str
    stk_nm: str
    cur_prc: str = "0"
    flu_rt: str = "0"


class SectorReport(BaseModel):
    id: int
    report_date: str
    thema_grp_cd: str
    thema_nm: str
    stk_num: int = 0
    flu_rt: float = 0.0
    dt_prft_rt: float = 0.0
    main_stk: Optional[str] = None
    rising_stk_num: int = 0
    fall_stk_num: int = 0
    rank_no: int = 0
    stocks: List[SectorStock] = []
    created_at: Optional[str] = None


@router.get("/sector-report/top-themes", response_model=dict[str, List[str]])
def top_themes(
    dates: str = Query(..., description="콤마 구분 YYYY-MM-DD 목록"),
    limit: int = Query(3, description="날짜별 최대 테마 수"),
):
    """여러 날짜의 상위 주도 테마명 목록 (날짜별 rank_no 순)"""
    try:
        date_list = [d.strip() for d in dates.split(",") if d.strip()]
        if not date_list:
            return {}
        return get_top_themes_by_dates(date_list, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sector-report/{report_date}", response_model=List[SectorReport])
def list_sector_reports(report_date: str):
    """특정 날짜의 주도 섹터 목록 (순위순, 구성종목 포함)"""
    try:
        results = get_sector_reports_by_date(report_date)
        if not results:
            raise HTTPException(status_code=404, detail="해당 날짜의 섹터 리포트가 없습니다")
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class GapStat(BaseModel):
    wins: int = 0
    losses: int = 0
    flats: int = 0
    total: int = 0


@router.get("/stock-report/gap-stats", response_model=dict[str, GapStat])
def gap_stats(dates: str = Query(..., description="콤마 구분 YYYY-MM-DD 목록")):
    """여러 날짜의 Top 10 갭 체크 승/패 통계 (KRX 우선, 폴백 NXT)"""
    try:
        date_list = [d.strip() for d in dates.split(",") if d.strip()]
        if not date_list:
            return {}
        return get_gap_stats_by_dates(date_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-report/dates", response_model=List[str])
def list_report_dates(limit: int = Query(30, description="최대 조회 일수")):
    """리포트가 존재하는 날짜 목록"""
    try:
        return get_stock_report_dates(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-report/history/{stock_code}", response_model=List[StockReport])
def list_reports_by_stock(stock_code: str, limit: int = Query(5, description="최대 조회 일수")):
    """특정 종목의 최근 N일 리포트 목록 (최신순)"""
    try:
        results = get_stock_report_history(stock_code, days=limit)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-report/{report_date}", response_model=List[StockReport])
def list_reports_by_date(report_date: str):
    """특정 날짜의 전체 종목 리포트 목록 (점수순)"""
    try:
        results = get_stock_reports_by_date(report_date)
        if not results:
            raise HTTPException(status_code=404, detail="해당 날짜의 리포트가 없습니다")
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-report/{report_date}/{stock_code}", response_model=StockReportDetail)
def get_report_detail(report_date: str, stock_code: str):
    """특정 날짜 + 종목의 상세 리포트 (최근 5일 수급 동향 포함)"""
    try:
        report = get_stock_report(report_date, stock_code)
        if not report:
            raise HTTPException(status_code=404, detail="해당 리포트가 없습니다")

        content_analyses = get_content_by_stock_and_date(
            stock_code, report_date
        )

        return {"report": report, "content_analyses": content_analyses}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
