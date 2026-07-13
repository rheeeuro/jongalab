"""스케줄러 잡 실행 이력 라우트 (admin 전용 — api.py 에서 require_admin 의존성 주입).

workers/scheduler.py 가 남긴 job_run 을 관리자 워커 현황 페이지에 제공한다. 조회 전용.
"""
from fastapi import APIRouter, HTTPException, Query

from core.repository import job_run

router = APIRouter(prefix="/api/job-runs", tags=["job-runs"])


@router.get("")
def list_job_runs(days: int = Query(default=2, ge=1, le=14)):
    """잡별 최신 상태(latest) + 최근 days 일 실행 이력(runs, 최신순)."""
    try:
        return {
            "latest": job_run.get_latest_per_job(),
            "runs": job_run.get_recent_runs(days),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
