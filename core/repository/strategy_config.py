"""전략 설정 데이터 접근"""
import json
from datetime import datetime

from core.db import get_db


# StrategyConfig 클래스의 기본값 (DB에 값이 없을 때 사용)
_DEFAULTS = {
    "MIN_TRADING_VALUE": 100_000_000_000,
    "PREFERRED_TRADING_VALUE": 200_000_000_000,
    "MIN_MARKET_CAP": 200_000_000_000,
    "TOP_N_BY_VALUE": 20,
    "MA_PERIODS": [5, 10, 20],
    "MIN_INST_NET_BUY_AMT": 1_000_000_000,
    "MIN_FRGN_NET_BUY_AMT": 1_000_000_000,
    "SUPPLY_CHECK_DAYS": 5,
    "SUPPLY_RECENCY_WEIGHTS": [0.3, 0.5, 0.8, 1.4, 3.0],
    "SUPPLY_DOUBLE_BUY_BASE_SCORE": 12,
    "SUPPLY_DOUBLE_BUY_AMOUNT_SCORE": 4,
    "SUPPLY_INST_BUY_BASE_SCORE": 8,
    "SUPPLY_INST_BUY_AMOUNT_SCORE": 3,
    "SUPPLY_FRGN_BUY_BASE_SCORE": 5,
    "SUPPLY_FRGN_BUY_AMOUNT_SCORE": 2,
    "SUPPLY_PERSONAL_SELL_SCORE": 3,
    "SUPPLY_PERSONAL_BUY_PENALTY": 3,
    "SUPPLY_SMART_PERSONAL_SELL_SCORE": 5,
    "SUPPLY_SMART_PERSONAL_BUY_PENALTY": 8,
    "SUPPLY_DOUBLE_STREAK_BONUS": [0, 0, 8, 15, 22, 30],
    "SUPPLY_INST_STREAK_BONUS": [0, 0, 5, 10, 16, 22],
    "SUPPLY_FRGN_STREAK_BONUS": [0, 0, 3, 6, 9, 12],
    "SUPPLY_CUMULATIVE_FRGN_INST_SCORE": 20,
    "SUPPLY_CUMULATIVE_INST_SCORE": 12,
    "SUPPLY_CUMULATIVE_SMART_PERSONAL_SELL_SCORE": 15,
    "SUPPLY_CUMULATIVE_SMART_PERSONAL_BUY_PENALTY": 20,
    "SUPPLY_RECENT_DOUBLE_BUY_SCORE": 20,
    "SUPPLY_TODAY_DOUBLE_BUY_SCORE": 15,
    "SUPPLY_TODAY_INST_BUY_SCORE": 8,
    "SUPPLY_TODAY_SMART_PERSONAL_SELL_SCORE": 8,
    "SUPPLY_TODAY_DOUBLE_SELL_PENALTY": 20,
    "SUPPLY_FOREIGN_SIGNAL_BOOST_MARGIN": 5,
    "TOP_THEME_COUNT": 8,
    "THEME_PERIOD_DAYS": "10",
    "THEME_STOCK_BONUS": 15,
    "CONTENT_SCORE_MAX": 10,
    "EXCLUDE_KEYWORDS": [
        "ETF", "ETN", "KODEX", "TIGER", "KBSTAR",
        "ARIRANG", "SOL", "HANARO", "RISE",
    ],
}


def get_strategy_config() -> dict:
    """전략 설정 조회 (DB에 없으면 기본값 반환)"""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT config, updated_at FROM strategy_config WHERE id = 1")
        row = cursor.fetchone()
        if row:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            # 기본값에 DB값을 덮어씀 (새 필드 추가 시 자동 반영)
            merged = {**_DEFAULTS, **config}
            return merged
        return dict(_DEFAULTS)


def update_strategy_config(config: dict) -> dict:
    """전략 설정 저장 (UPSERT)"""
    # 기본값과 동일한 키만 저장 (알 수 없는 키 차단)
    filtered = {k: v for k, v in config.items() if k in _DEFAULTS}
    config_json = json.dumps(filtered, ensure_ascii=False)

    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO strategy_config (id, config)
               VALUES (1, %s)
               ON DUPLICATE KEY UPDATE config = %s""",
            (config_json, config_json),
        )
        conn.commit()

    return get_strategy_config()
