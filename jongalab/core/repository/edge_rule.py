"""Edge Ledger 데이터 접근 (edge_rule · edge_rule_daily).

가설(rule)은 candidate 로 태어나 rule_evaluator 가 매일 채점하고, 표본·성적이 차면
관리자 API 로만 live 승격된다(자동 승격 없음). raw SQL 은 여기서만.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from core.db import get_db

# exit_label 로 허용되는 결과 라벨 컬럼(daily_stock_report). 오타/오설정으로 영원히
# 준비 안 되는(readiness=False) rule 을 만드는 걸 막는다. 라벨 추가 시 여기 등록.
ALLOWED_EXIT_LABELS = (
    "next_open_ret", "next_high_ret", "next_low_ret", "next_close_ret",
    "nxt_open_ret", "gap_nxt_pct", "gap_krx_pct", "exec_leg_ret",
)


def _serialize(row: dict) -> dict:
    """JSON 컬럼 파싱 + 날짜/Decimal 직렬화."""
    for k in ("predicate", "stats", "matched"):
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


# ── edge_rule CRUD ──

def create_rule(
    name: str,
    family: str,
    description: str,
    predicate: list,
    exit_label: str = "exec_leg_ret",
    min_sample: int = 40,
    registered_at: str | None = None,
    status: str = "candidate",
    title: str | None = None,
) -> int:
    """신규 rule 등록. registered_at 미지정 시 오늘(사전 등록일). 반환: rule id.
    title 은 카드 제목(한글) — NULL 이면 프론트가 name 슬러그로 폴백."""
    pred = json.dumps(predicate, ensure_ascii=False)
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO edge_rule
               (name, title, family, description, predicate, exit_label, status, min_sample, registered_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, CURDATE()))""",
            (name, title, family, description, pred, exit_label, status, int(min_sample), registered_at),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_rules(status: str | None = None, exclude_retired: bool = False) -> list[dict]:
    """rule 목록. status 지정 시 그 상태만, exclude_retired 면 retired 제외(evaluator 용)."""
    cond, params = "", []
    if status:
        cond, params = " WHERE status = %s", [status]
    elif exclude_retired:
        cond = " WHERE status <> 'retired'"
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT * FROM edge_rule{cond} ORDER BY family, name", tuple(params)
        )
        return [_serialize(r) for r in cursor.fetchall()]


def get_rule(rule_id: int) -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM edge_rule WHERE id = %s", (rule_id,))
        row = cursor.fetchone()
        return _serialize(row) if row else None


def get_rule_by_name(name: str) -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM edge_rule WHERE name = %s", (name,))
        row = cursor.fetchone()
        return _serialize(row) if row else None


def update_rule_stats(rule_id: int, stats: dict) -> None:
    """evaluator 가 재계산한 누적 통계 캐시 갱신."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE edge_rule SET stats = %s WHERE id = %s",
            (json.dumps(stats, ensure_ascii=False, default=str), rule_id),
        )
        conn.commit()


def set_rule_status(rule_id: int, status: str) -> None:
    """상태 전이 — live 면 promoted_at, retired 면 retired_at 타임스탬프도 찍는다."""
    ts = ""
    if status == "live":
        ts = ", promoted_at = CURRENT_TIMESTAMP"
    elif status == "retired":
        ts = ", retired_at = CURRENT_TIMESTAMP"
    with get_db() as (conn, cursor):
        cursor.execute(
            f"UPDATE edge_rule SET status = %s{ts} WHERE id = %s", (status, rule_id)
        )
        conn.commit()


def count_promoted_in_month(year: int, month: int) -> int:
    """해당 연·월에 live 로 승격된 rule 수 (월 승격 상한 게이트용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT COUNT(*) AS c FROM edge_rule
               WHERE promoted_at IS NOT NULL
                 AND YEAR(promoted_at) = %s AND MONTH(promoted_at) = %s""",
            (year, month),
        )
        return int(cursor.fetchone()["c"])


# ── edge_rule_daily ──

def upsert_rule_daily(
    rule_id: int, report_date: str, n_matched: int,
    mean_net_ret: float | None, matched: list,
) -> None:
    """rule×날짜 평가 결과 upsert(재실행 멱등)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO edge_rule_daily (rule_id, report_date, n_matched, mean_net_ret, matched)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 n_matched = VALUES(n_matched),
                 mean_net_ret = VALUES(mean_net_ret),
                 matched = VALUES(matched)""",
            (rule_id, report_date, int(n_matched), mean_net_ret,
             json.dumps(matched, ensure_ascii=False, default=str)),
        )
        conn.commit()


def get_scored_dates(rule_id: int) -> set[str]:
    """이미 채점된 report_date 집합 (catch-up 에서 제외용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT report_date FROM edge_rule_daily WHERE rule_id = %s", (rule_id,)
        )
        return {
            r["report_date"].isoformat() if isinstance(r["report_date"], (date, datetime))
            else str(r["report_date"])
            for r in cursor.fetchall()
        }


def get_rule_daily(rule_id: int, days: int = 60) -> list[dict]:
    """일별 성적 시계열(최신 days 일, 오래된→최신). 스코어보드 차트용.

    matched(일별 매칭 종목 전체 JSON)는 제외한다 — 광역 rule 은 하루 수십 종목이라
    60일치를 다 실으면 페이로드가 수백 KB 로 자란다. 최신 매칭은 get_latest_matched 로.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT id, rule_id, report_date, n_matched, mean_net_ret, created_at FROM (
                   SELECT id, rule_id, report_date, n_matched, mean_net_ret, created_at
                     FROM edge_rule_daily WHERE rule_id = %s
                    ORDER BY report_date DESC LIMIT %s
               ) t ORDER BY report_date ASC""",
            (rule_id, int(days)),
        )
        return [_serialize(r) for r in cursor.fetchall()]


def get_latest_matched(rule_id: int) -> dict | None:
    """매칭이 있었던 가장 최신 날짜의 {report_date, matched} — 상세 뷰 '최근 매칭 종목'용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT report_date, matched FROM edge_rule_daily
                WHERE rule_id = %s AND n_matched > 0
                ORDER BY report_date DESC LIMIT 1""",
            (rule_id,),
        )
        row = cursor.fetchone()
        return _serialize(row) if row else None


def get_rule_daily_since(rule_id: int, since: str) -> list[dict]:
    """registered_at(=since) 이후 채점 결과 전체(오래된→최신) — 누적 통계 재계산용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM edge_rule_daily
               WHERE rule_id = %s AND report_date >= %s
               ORDER BY report_date ASC""",
            (rule_id, since),
        )
        return [_serialize(r) for r in cursor.fetchall()]
