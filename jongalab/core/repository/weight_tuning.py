"""가중치 튜닝 제안 데이터 접근 (weight_tuning_proposal).

주간 워커가 GPT 제안을 status='pending' 으로 저장하고, 관리자가 대시보드에서 검토 후
승인(approved)하면 strategy_config 에 반영된다. 자동 적용은 하지 않는다.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from core.db import get_db


def _serialize(row: dict) -> dict:
    """JSON 컬럼 파싱 + 날짜/Decimal 직렬화."""
    for k in ("current_weights", "proposed_weights", "dataset"):
        v = row.get(k)
        if isinstance(v, str):
            try:
                row[k] = json.loads(v)
            except (ValueError, TypeError):
                row[k] = None
    for k, v in list(row.items()):
        if isinstance(v, (date, datetime)):
            row[k] = v.isoformat()
        elif isinstance(v, Decimal):
            row[k] = float(v)
    return row


def save_proposal(
    week_start: str,
    week_end: str,
    sample_count: int,
    winners_count: int,
    losers_count: int,
    total_realized_pnl: int,
    current_weights: dict,
    proposed_weights: dict,
    rationale: str,
    dataset: list | dict,
) -> int:
    """제안 저장 (주 단위 UPSERT). 같은 주에 재실행하면 최신 제안으로 덮어쓰고 pending 으로 되돌린다.
    반환: 제안 id."""
    cw = json.dumps(current_weights, ensure_ascii=False)
    pw = json.dumps(proposed_weights, ensure_ascii=False)
    ds = json.dumps(dataset, ensure_ascii=False, default=str)
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO weight_tuning_proposal
               (week_start, week_end, status, sample_count, winners_count, losers_count,
                total_realized_pnl, current_weights, proposed_weights, rationale, dataset)
               VALUES (%s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 week_end = VALUES(week_end), status = 'pending',
                 sample_count = VALUES(sample_count), winners_count = VALUES(winners_count),
                 losers_count = VALUES(losers_count), total_realized_pnl = VALUES(total_realized_pnl),
                 current_weights = VALUES(current_weights), proposed_weights = VALUES(proposed_weights),
                 rationale = VALUES(rationale), dataset = VALUES(dataset),
                 created_at = CURRENT_TIMESTAMP, applied_at = NULL""",
            (week_start, week_end, sample_count, winners_count, losers_count,
             total_realized_pnl, cw, pw, rationale, ds),
        )
        # 이전 주의 미검토(pending) 제안은 만료 처리 — 이번 주 제안만 검토 대상으로 남긴다.
        cursor.execute(
            "UPDATE weight_tuning_proposal SET status = 'expired' "
            "WHERE status = 'pending' AND week_start <> %s",
            (week_start,),
        )
        conn.commit()
        cursor.execute(
            "SELECT id FROM weight_tuning_proposal WHERE week_start = %s", (week_start,)
        )
        row = cursor.fetchone()
        return int(row["id"]) if row else 0


def get_proposal(proposal_id: int) -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM weight_tuning_proposal WHERE id = %s", (proposal_id,)
        )
        row = cursor.fetchone()
        return _serialize(row) if row else None


def get_latest_proposal() -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM weight_tuning_proposal ORDER BY week_start DESC, id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return _serialize(row) if row else None


def list_proposals(limit: int = 20) -> list[dict]:
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM weight_tuning_proposal ORDER BY week_start DESC, id DESC LIMIT %s",
            (int(limit),),
        )
        return [_serialize(r) for r in cursor.fetchall()]


def mark_applied(proposal_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE weight_tuning_proposal SET status = 'approved', applied_at = CURRENT_TIMESTAMP "
            "WHERE id = %s",
            (proposal_id,),
        )
        conn.commit()


def mark_rejected(proposal_id: int) -> None:
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE weight_tuning_proposal SET status = 'rejected' WHERE id = %s",
            (proposal_id,),
        )
        conn.commit()
