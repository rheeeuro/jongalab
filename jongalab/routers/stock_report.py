"""종목일간리포트 라우트"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.backtest import score_breakdown
from core.repository.strategy_config import get_strategy_config
from core.repository import (
    get_stock_report,
    get_stock_report_history,
    get_stock_reports_by_date,
    get_stock_report_dates,
    get_sector_reports_by_date,
    get_content_by_stock_and_date,
    get_gap_stats_by_dates,
    get_top_picks_by_dates,
    get_top_themes_by_dates,
    get_record_summary,
)

router = APIRouter(prefix="/api", tags=["stock-report"])


class SupplyHistoryItem(BaseModel):
    date: str = ""
    inst_net_buy: int = 0
    frgn_net_buy: int = 0
    indv_net_buy: int = 0
    prog_net_buy: int = 0


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
    news_count: int = 0
    news_unique_count: int = 0
    news_pm_count: int = 0
    news_first_today: bool = False
    news_prior_avg: Optional[float] = None
    news_summary: Optional[str] = None
    news_sentiment: Optional[int] = None
    news_catalyst: Optional[str] = None
    # 재료 지속성 라벨 (sql/40, 축·합성 v2 = sql/52) — 관찰 전용(candidate rule 표본).
    # 화면은 '미검증' 톤으로 노출한다. 등급을 만든 축을 함께 실어야 육안 감사가 된다 —
    # v2 에서 등급을 가르는 축이 amount_locked → milestone_horizon 으로 바뀌었으므로
    # 시점·규모를 빼면 화면이 '더 이상 등급에 쓰이지 않는 축'만 보여주게 된다.
    news_next_milestone: Optional[bool] = None
    news_milestone_horizon: Optional[str] = None
    news_amount_locked: Optional[bool] = None
    news_material_size_ratio: Optional[float] = None
    news_driver_scope: Optional[str] = None
    news_stage: Optional[str] = None
    news_durability: Optional[str] = None
    news_durability_v: Optional[int] = None
    news_label_reason: Optional[str] = None
    news_followup_days: Optional[int] = None
    news_headlines: List[str] = []
    score: float = 0.0
    # 선정 근거(sql/43) — hybrid/rules 모드에서 이 종목을 뽑은 live selector rule name 콤마 목록.
    # NULL 이면 점수순 선정. 화면은 이 값으로 '룰 선정' 배지 + 실제 점수 순위를 함께 낸다.
    rule_names: Optional[str] = None
    reason: str = ""
    rank_no: int = 0
    gap_nxt_price: Optional[int] = None
    gap_nxt_pct: Optional[float] = None
    gap_krx_price: Optional[int] = None
    gap_krx_pct: Optional[float] = None
    gap_checked_at: Optional[str] = None
    # 무상증자 권리락 조정 배정비율(sql/50) — 값이 있으면 gap_*_pct 는 조정 기준가 대비다.
    gap_ex_rights_ratio: Optional[float] = None
    exec_leg_ret: Optional[float] = None
    exec_leg_venue: Optional[str] = None
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


class ScoreBreakdownItem(BaseModel):
    key: str
    label: str
    points: float = 0.0      # 100점 환산 획득 점수
    max_points: float = 0.0  # 100점 환산 만점


class ScoreBreakdownPenalty(BaseModel):
    key: str
    label: str
    points: float = 0.0      # 감점이라 음수


class ScoreBreakdown(BaseModel):
    """종합점수 구성 — 화면 게이지 전용.

    가중치가 주간 튜닝(`strategy_config`)으로 바뀌므로 **화면이 아니라 서버가** 낸다.
    ⚠️ 지금 가중치로 다시 계산한 값이라, 튜닝 이후에 조회한 과거 리포트는 저장된
    `score` 와 `total` 이 다를 수 있다(화면이 그 차이를 밝힌다).
    """
    items: List[ScoreBreakdownItem] = []
    penalty: Optional[ScoreBreakdownPenalty] = None
    total: float = 0.0


class StockReportDetail(BaseModel):
    report: StockReport
    content_analyses: List[ContentAnalysisItem] = []
    score_breakdown: Optional[ScoreBreakdown] = None


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


class RecordDay(BaseModel):
    date: str
    pct: float = 0.0


class RecordSummary(BaseModel):
    days: int = 0
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    picks: int = 0
    wins: int = 0
    losses: int = 0
    flats: int = 0
    win_rate: float = 0.0
    avg_gap_pct: float = 0.0
    # 실체결 손익률은 매매 경로에서 채워져 갭보다 표본이 적을 수 있다 —
    # 화면이 갭과 같은 모수로 읽지 않게 표본 수를 함께 내린다.
    avg_exec_ret: Optional[float] = None
    exec_samples: int = 0
    exec_days: int = 0
    exec_from_date: Optional[str] = None
    exec_to_date: Optional[str] = None
    best_day: Optional[RecordDay] = None
    worst_day: Optional[RecordDay] = None


@router.get("/stock-report/record-summary", response_model=Optional[RecordSummary])
def record_summary(days: int = Query(20, ge=1, le=250, description="집계할 최근 거래일 수")):
    """최근 N 거래일 선정 종목의 누적 성적 (승률·평균 갭·평균 실체결 손익률)"""
    try:
        return get_record_summary(days) or None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TopPick(BaseModel):
    stock_code: str
    stock_name: str
    score: float = 0.0


@router.get("/stock-report/top-picks", response_model=dict[str, TopPick])
def top_picks(dates: str = Query(..., description="콤마 구분 YYYY-MM-DD 목록")):
    """여러 날짜의 1등 종목(rank_no=1)을 한 번에 조회 (아카이브 캘린더용)"""
    try:
        date_list = [d.strip() for d in dates.split(",") if d.strip()]
        if not date_list:
            return {}
        return get_top_picks_by_dates(date_list)
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

        return {
            "report": report,
            "content_analyses": content_analyses,
            "score_breakdown": score_breakdown(report, get_strategy_config()),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
