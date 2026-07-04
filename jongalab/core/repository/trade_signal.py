"""매수 시그널 핸드오프 — closing_bet 후보를 trading DB(trade_signal)에 적재.

두 도메인(jongalab 분석 ↔ trading 집행)의 유일한 결합점. trading 이 소비한다.
closing_bet 은 9~18시 30분마다 재실행되므로 (trade_date, stk_cd) UNIQUE 로 멱등 처리:
재실행 시 점수·순위를 갱신하고 status 는 보존하되, 이전에 'expired' 로 정리됐다가 이번
top-N 에 다시 든 종목은 'pending' 으로 되살린다(done/skipped/rejected/executing 은 보존 →
이미 집행했거나 처리한 종목은 재집행하지 않음).
이번 top-N 에서 빠진 잔여 pending 은 'expired' 로 정리한다 — 그러지 않으면 하루 중
한 번이라도 top-N 에 들었던 종목이 매수 큐에 계속 남아(리포트와 불일치) 의도치 않게 집행된다.
"""
import logging

from core.db import get_trading_db

logger = logging.getLogger("TradeSignal")


# rule_names 컬럼 존재 여부(Phase 4 마이그레이션 적용 여부) — 프로세스당 1회만 프로브.
# 워커는 단발 프로세스라 마이그레이션 적용은 다음 실행부터 자연 반영된다.
_HAS_RULE_NAMES: bool | None = None


def _has_rule_names(cursor) -> bool:
    global _HAS_RULE_NAMES
    if _HAS_RULE_NAMES is None:
        cursor.execute(
            """SELECT COUNT(*) AS c FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE()
                 AND TABLE_NAME = 'trade_signal' AND COLUMN_NAME = 'rule_names'"""
        )
        _HAS_RULE_NAMES = bool(cursor.fetchone()["c"])
    return _HAS_RULE_NAMES


def push_trade_signals(trade_date: str, candidates: list[dict]) -> int:
    """후보 목록을 trade_signal 에 upsert. 반영된 행 수 반환.

    candidates: [{stk_cd, stk_nm, rank_no, score, rule_names?}, ...]
    신규는 status='pending' 으로 삽입, 기존은 stk_nm/rank_no/score(+rule_names) 갱신 +
    expired→pending 복귀(done/skipped/rejected/executing 보존).
    rule_names 는 선정 근거 edge_rule name 콤마 목록(legacy 선정은 None). 컬럼이 없으면
    (Phase 4 마이그레이션 미적용) 조용히 무시하고 기존 컬럼만 쓴다(하위호환).
    SQL 은 컬럼 목록에서 한 번만 조립한다 — 유무 분기용 문장 2벌 유지 금지(드리프트 방지).
    """
    if not candidates:
        return 0

    codes = [c["stk_cd"] for c in candidates]
    with get_trading_db() as (conn, cursor):
        # 갱신 대상 컬럼(candidates dict 키와 1:1). rule_names 는 마이그레이션 적용 시에만.
        value_cols = ["stk_nm", "rank_no", "score"]
        if _has_rule_names(cursor):
            value_cols.append("rule_names")
        cols = ["trade_date", "stk_cd", *value_cols]
        rows = [
            (trade_date, c["stk_cd"], *(c.get(k) for k in value_cols))
            for c in candidates
        ]
        updates = ",\n                       ".join(f"{k} = VALUES({k})" for k in value_cols)
        cursor.executemany(
            f"""INSERT INTO trade_signal ({", ".join(cols)}, status)
               VALUES ({", ".join(["%s"] * len(cols))}, 'pending')
               ON DUPLICATE KEY UPDATE
                       {updates},
                       status = IF(status = 'expired', 'pending', status),
                       updated_at = CURRENT_TIMESTAMP""",
            rows,
        )
        upserted = cursor.rowcount

        # 이번 후보에서 빠진 잔여 pending 만료 (done/skipped/executing/rejected 는 보존)
        placeholders = ",".join(["%s"] * len(codes))
        cursor.execute(
            f"""UPDATE trade_signal SET status = 'expired'
                WHERE trade_date = %s AND status = 'pending'
                  AND stk_cd NOT IN ({placeholders})""",
            [trade_date, *codes],
        )
        if cursor.rowcount:
            logger.info("탈락 pending 시그널 %d건 만료 처리 (%s)", cursor.rowcount, trade_date)

        conn.commit()
        return upserted
