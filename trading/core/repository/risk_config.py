"""리스크 한도 설정 데이터 접근 (단일행 id=1, JSON blob).

대시보드에서 수정하고 RiskConfig.load_from_db() 가 읽는다.
jongalab strategy_config 와 동일 패턴: 기본값 위에 DB값을 덮어써 새 필드 자동 반영.
"""
import json

from core.db import get_db


# RiskConfig 기본값 (DB에 값이 없을 때 사용)
_DEFAULTS = {
    "MAX_ORDERS_PER_DAY": 10,          # 일일 최대 주문 건수
    "MAX_NOTIONAL_PER_NAME": 5_000_000,  # 종목당 최대 명목금액(원)
    "MAX_DAILY_LOSS": 3_000_000,       # 일일 최대 손실(원) → 초과 시 서킷브레이커
    "MAX_POSITIONS": 5,                # 동시 보유 종목수
}


def get_risk_config() -> dict:
    """리스크 설정 조회 (DB에 없으면 기본값)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT config FROM risk_config WHERE id = 1")
        row = cursor.fetchone()
        if row:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            return {**_DEFAULTS, **config}
        return dict(_DEFAULTS)


def update_risk_config(config: dict) -> dict:
    """리스크 설정 저장 (UPSERT). 알 수 없는 키는 차단."""
    filtered = {k: int(v) for k, v in config.items() if k in _DEFAULTS}
    config_json = json.dumps(filtered, ensure_ascii=False)
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO risk_config (id, config)
               VALUES (1, %s)
               ON DUPLICATE KEY UPDATE config = %s""",
            (config_json, config_json),
        )
        conn.commit()
    return get_risk_config()
