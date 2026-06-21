"""전략 설정 라우트"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from core.repository import get_strategy_config, update_strategy_config

router = APIRouter(prefix="/api", tags=["strategy-config"])


class StrategyConfigResponse(BaseModel):
    # 필터 임계값
    MIN_TRADING_VALUE: int = 0
    PREFERRED_TRADING_VALUE: int = 0
    MIN_MARKET_CAP: int = 0
    TOP_N_BY_VALUE: int = 20
    # 이동평균
    MA_PERIODS: List[int] = [5, 10, 20]
    # 수급 기준
    MIN_INST_NET_BUY_AMT: int = 0
    MIN_FRGN_NET_BUY_AMT: int = 0
    SUPPLY_CHECK_DAYS: int = 5
    SUPPLY_RECENCY_WEIGHTS: List[float] = [0.3, 0.5, 0.8, 1.4, 3.0]
    SUPPLY_DOUBLE_BUY_BASE_SCORE: int = 12
    SUPPLY_DOUBLE_BUY_AMOUNT_SCORE: int = 4
    SUPPLY_INST_BUY_BASE_SCORE: int = 8
    SUPPLY_INST_BUY_AMOUNT_SCORE: int = 3
    SUPPLY_FRGN_BUY_BASE_SCORE: int = 5
    SUPPLY_FRGN_BUY_AMOUNT_SCORE: int = 2
    SUPPLY_PERSONAL_SELL_SCORE: int = 3
    SUPPLY_PERSONAL_BUY_PENALTY: int = 3
    SUPPLY_SMART_PERSONAL_SELL_SCORE: int = 5
    SUPPLY_SMART_PERSONAL_BUY_PENALTY: int = 8
    SUPPLY_DOUBLE_STREAK_BONUS: List[int] = [0, 0, 8, 15, 22, 30]
    SUPPLY_INST_STREAK_BONUS: List[int] = [0, 0, 5, 10, 16, 22]
    SUPPLY_FRGN_STREAK_BONUS: List[int] = [0, 0, 3, 6, 9, 12]
    SUPPLY_CUMULATIVE_FRGN_INST_SCORE: int = 20
    SUPPLY_CUMULATIVE_INST_SCORE: int = 12
    SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE: int = 15
    SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY: int = 20
    SUPPLY_RECENT_DOUBLE_BUY_SCORE: int = 20
    SUPPLY_TODAY_DOUBLE_BUY_SCORE: int = 15
    SUPPLY_TODAY_INST_BUY_SCORE: int = 8
    SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE: int = 8
    SUPPLY_TODAY_DOUBLE_SELL_PENALTY: int = 20
    SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN: int = 5
    # 테마
    TOP_THEME_COUNT: int = 8
    THEME_PERIOD_DAYS: str = "10"
    THEME_STOCK_BONUS: int = 15
    # 콘텐츠 분석
    CONTENT_SCORE_MAX: int = 10
    # 종합점수 구성 가중치 (주간 매매성과 기반 GPT 튜닝 대상)
    SCORE_SUPPLY_BONUS: float = 40.0
    SCORE_MA_ALIGNED_BONUS: int = 10
    SCORE_NEAR_HIGH_BONUS: int = 10
    SCORE_PREFERRED_VALUE_BONUS: int = 15
    SCORE_MIN_VALUE_BONUS: int = 8
    SCORE_LEADER_BONUS: int = 10
    SCORE_EXTRA_SUPPLY_DAY_BONUS: int = 3
    # 제외 키워드
    EXCLUDE_KEYWORDS: List[str] = []


@router.get("/strategy-config", response_model=StrategyConfigResponse)
def get_config():
    """현재 전략 설정 조회"""
    try:
        return get_strategy_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/strategy-config", response_model=StrategyConfigResponse)
def put_config(body: StrategyConfigResponse):
    """전략 설정 업데이트"""
    try:
        return update_strategy_config(body.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
