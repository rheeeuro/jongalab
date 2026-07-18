"""
Kiwoom Data API — 키움 REST 데이터 조회 전용 FastAPI 서버 (localhost :8001).

jongalab 메인 앱이 core.kiwoom_client.KiwoomRestClient 를 통해 HTTP 로 호출한다.
각 엔드포인트는 요청마다 ensure_token() 으로 토큰을 보장한 뒤 키움 응답 dict 를
그대로 반환한다(소비자가 원본 필드를 그대로 읽으므로 가공하지 않는다).
"""
import logging

from fastapi import FastAPI
from pydantic import BaseModel

from core.config import DB_CONFIG  # noqa: F401  (import 시 루트 .env 로드)
from core.logging_setup import setup_logging
from core.kiwoom_api import KiwoomConfig, KiwoomRestAPI
from core.repository import kiwoom_token as token_repo

setup_logging()
logger = logging.getLogger("KiwoomAPI")

app = FastAPI(title="Kiwoom Data API")

# 모듈 레벨 싱글턴 (토큰은 공유 DB 에서 ensure_token 으로 로드/갱신)
_api = KiwoomRestAPI(KiwoomConfig())


def api() -> KiwoomRestAPI:
    """요청마다 토큰 보장 후 키움 API 인스턴스 반환."""
    _api.ensure_token()
    return _api


# ── 요청 바디 ──
class StkCd(BaseModel):
    stk_cd: str


class DailyChart(BaseModel):
    stk_cd: str
    dt: str = ""
    upd_stk_prc: str = "1"


class MinuteChartPages(BaseModel):
    stk_cd: str
    tic_scope: str = "60"
    base_dt: str = ""
    max_pages: int = 5


class ShortSaleTrend(BaseModel):
    stk_cd: str
    strt_dt: str = ""   # YYYYMMDD, 빈값=최근 30일
    end_dt: str = ""    # YYYYMMDD, 빈값=오늘


class CreditTrend(BaseModel):
    stk_cd: str
    dt: str = ""        # YYYYMMDD, 빈값=오늘
    qry_tp: str = "1"   # 1:융자, 2:대주


class MarketTp(BaseModel):
    mrkt_tp: str = "001"


class StockList(BaseModel):
    mrkt_tp: str = "0"  # 0=코스피, 10=코스닥


class ProgramTrade(BaseModel):
    mrkt_tp: str = "P00101"


class ProgramHourly(BaseModel):
    stk_cd: str
    date: str = ""          # 빈값=당일 (YYYYMMDD)
    max_pages: int = 8      # 페이지당 200행 ≈ 25분
    until_tm: str = ""      # "HHMMSS" — 이 시각 이전 행 도달 시 조기 중단


class AfterCloseInvestor(BaseModel):
    mrkt_tp: str = "000"     # 000:전체, 001:코스피, 101:코스닥
    amt_qty_tp: str = "1"    # 1:금액(백만원), 2:수량
    trde_tp: str = "0"       # 0:순매수, 1:매수, 2:매도
    stex_tp: str = "3"       # 1:KRX, 2:NXT, 3:통합
    max_pages: int = 5


class AfterHoursFluRank(BaseModel):
    mrkt_tp: str = "000"    # 000:전체, 001:코스피, 101:코스닥
    sort_base: str = "1"    # 1:상승률, 3:하락률
    stk_cnd: str = "16"     # 16:ETF+ETN제외


class ThemeGroups(BaseModel):
    date_tp: str = "1"
    flu_pl_amt_tp: str = "3"
    stex_tp: str = "3"


class ThemeStocks(BaseModel):
    thema_grp_cd: str
    date_tp: str = "10"
    stex_tp: str = "3"


# ── 헬스 ──
@app.get("/health")
def health():
    """DB 연결·토큰 보유 여부 점검."""
    has_token = False
    db_ok = True
    try:
        tok = token_repo.get_token()
        has_token = bool(tok and tok.get("access_token"))
    except Exception as e:
        db_ok = False
        logger.warning("health: DB 점검 실패: %s", e)
    return {"status": "ok", "service": "kiwoom", "db": db_ok, "has_token": has_token}


@app.get("/")
def root():
    return {"status": "ok", "service": "Kiwoom Data API"}


# ── 데이터 엔드포인트 (소비자가 실제 사용하는 11종) ──
@app.post("/stock/basic-info")
def stock_basic_info(b: StkCd):
    return api().get_stock_basic_info(b.stk_cd)


@app.post("/stock/detail-info")
def stock_detail_info(b: StkCd):
    return api().get_stock_detail_info(b.stk_cd)


@app.post("/stock/broker")
def stock_broker(b: StkCd):
    return api().get_stock_broker(b.stk_cd)


@app.post("/stock/list")
def stock_list(b: StockList):
    return api().get_stock_list(mrkt_tp=b.mrkt_tp)


@app.post("/stock/intraday-investor")
def intraday_investor(b: StkCd):
    return api().get_intraday_investor(b.stk_cd)


@app.post("/stock/short-sale-trend")
def short_sale_trend(b: ShortSaleTrend):
    return api().get_short_sale_trend(b.stk_cd, strt_dt=b.strt_dt, end_dt=b.end_dt)


@app.post("/stock/lending-trend")
def lending_trend(b: ShortSaleTrend):
    return api().get_stock_lending_trend(b.stk_cd, strt_dt=b.strt_dt, end_dt=b.end_dt)


@app.post("/stock/credit-trend")
def credit_trend(b: CreditTrend):
    return api().get_credit_trade_trend(b.stk_cd, dt=b.dt, qry_tp=b.qry_tp)


@app.post("/stock/execution-strength-hourly")
def execution_strength_hourly(b: StkCd):
    return api().get_execution_strength_hourly(b.stk_cd)


@app.post("/stock/execution-strength-daily")
def execution_strength_daily(b: StkCd):
    return api().get_execution_strength_daily(b.stk_cd)


@app.post("/stock/after-hours-price")
def after_hours_price(b: StkCd):
    return api().get_after_hours_single_price(b.stk_cd)


@app.post("/chart/daily")
def daily_chart(b: DailyChart):
    return api().get_daily_chart(b.stk_cd, dt=b.dt, upd_stk_prc=b.upd_stk_prc)


@app.post("/chart/minute-pages")
def minute_chart_pages(b: MinuteChartPages):
    return api().get_minute_chart_pages(
        b.stk_cd, tic_scope=b.tic_scope, base_dt=b.base_dt, max_pages=b.max_pages
    )


@app.post("/rank/trading-value")
def trading_value_rank(b: MarketTp):
    return api().get_trading_value_rank(mrkt_tp=b.mrkt_tp)


@app.post("/market/after-close-investor")
def after_close_investor(b: AfterCloseInvestor):
    return api().get_after_close_investor(
        mrkt_tp=b.mrkt_tp, amt_qty_tp=b.amt_qty_tp,
        trde_tp=b.trde_tp, stex_tp=b.stex_tp, max_pages=b.max_pages,
    )


@app.post("/rank/after-hours-flu")
def after_hours_flu_rank(b: AfterHoursFluRank):
    return api().get_after_hours_flu_rank(
        mrkt_tp=b.mrkt_tp, sort_base=b.sort_base, stk_cnd=b.stk_cnd
    )


@app.post("/program-trade/by-stock")
def program_trade_by_stock(b: ProgramTrade):
    return api().get_program_trade_by_stock(mrkt_tp=b.mrkt_tp)


@app.post("/program-trade/daily-trend")
def program_trade_daily_trend(b: StkCd):
    return api().get_program_daily_trend(b.stk_cd)


@app.post("/program-trade/hourly-trend")
def program_trade_hourly_trend(b: ProgramHourly):
    return api().get_program_trade_hourly(
        b.stk_cd, date=b.date, max_pages=b.max_pages, until_tm=b.until_tm
    )


@app.post("/inst-foreign/consecutive")
def inst_foreign_consecutive(b: MarketTp):
    return api().get_inst_foreign_consecutive(mrkt_tp=b.mrkt_tp)


@app.post("/theme/groups")
def theme_groups(b: ThemeGroups):
    return api().get_theme_groups(
        date_tp=b.date_tp, flu_pl_amt_tp=b.flu_pl_amt_tp, stex_tp=b.stex_tp
    )


@app.post("/theme/stocks")
def theme_stocks(b: ThemeStocks):
    return api().get_theme_stocks(
        thema_grp_cd=b.thema_grp_cd, date_tp=b.date_tp, stex_tp=b.stex_tp
    )
