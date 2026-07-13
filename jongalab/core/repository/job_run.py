"""통합 잡 스케줄러(workers/scheduler.py) 실행 이력 접근.

스케줄러가 잡을 spawn 하기 직전에 start_run 으로 running 행을 만들고,
종료 시 finish_run 으로 상태를 확정한다. 관리자 워커 현황 페이지와
실패 경보가 이 테이블을 본다. status: running/success/fail/timeout/aborted.
"""
from datetime import date, datetime

from core.db import get_db

FINAL_STATUSES = ("success", "fail", "timeout", "aborted")


def start_run(job_name: str, scheduled_at: datetime) -> int:
    """실행 시작 기록(running) 후 run id 반환."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO job_run (job_name, scheduled_at, started_at, status)
               VALUES (%s, %s, NOW(), 'running')""",
            (job_name, scheduled_at),
        )
        conn.commit()
        return cursor.lastrowid


def finish_run(run_id: int, status: str, exit_code: int | None = None,
               log_tail: str | None = None) -> None:
    """실행 종료 확정. status 는 FINAL_STATUSES 중 하나."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """UPDATE job_run
               SET status = %s, exit_code = %s, log_tail = %s, finished_at = NOW()
               WHERE id = %s""",
            (status, exit_code, log_tail, run_id),
        )
        conn.commit()


def sweep_stale_running() -> int:
    """running 잔류 행을 aborted 로 정리 — 스케줄러 재시작 직후 1회 호출.

    (스케줄러가 죽으면 자식 결과를 못 받아 running 이 남는다. 자식이 고아로
    완주했을 수도 있으나 결과를 알 수 없으므로 aborted 로 보수적으로 마감.)
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """UPDATE job_run
               SET status = 'aborted', finished_at = NOW(),
                   log_tail = '(스케줄러 재시작으로 결과 유실)'
               WHERE status = 'running'"""
        )
        conn.commit()
        return cursor.rowcount


def delete_old_runs(days: int = 60) -> int:
    """보존 기간이 지난 실행 이력 삭제 — 스케줄러 시작 시 호출."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "DELETE FROM job_run WHERE scheduled_at < NOW() - INTERVAL %s DAY",
            (days,),
        )
        conn.commit()
        return cursor.rowcount


def _serialize(row: dict) -> dict:
    for key in ("scheduled_at", "started_at", "finished_at", "created_at"):
        if isinstance(row.get(key), (date, datetime)):
            row[key] = row[key].isoformat(sep=" ")
    return row


def get_latest_per_job() -> list[dict]:
    """잡별 최신 실행 1건씩 (워커 현황 요약 카드용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT r.* FROM job_run r
               JOIN (SELECT job_name, MAX(id) AS max_id FROM job_run GROUP BY job_name) m
                 ON r.id = m.max_id
               ORDER BY r.job_name"""
        )
        return [_serialize(row) for row in cursor.fetchall()]


def get_recent_runs(days: int = 2, limit: int = 300) -> list[dict]:
    """최근 실행 이력 (최신순) — 워커 현황 상세 목록용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM job_run
               WHERE scheduled_at >= NOW() - INTERVAL %s DAY
               ORDER BY id DESC LIMIT %s""",
            (days, limit),
        )
        return [_serialize(row) for row in cursor.fetchall()]
