"""통합 잡 스케줄러 — PM2 cron_restart 계층을 대체하는 상시 워커.

JOBS 에 정의된 cron 시각마다 워커를 **서브프로세스**(`uv run ...`)로 spawn 한다.
워커 스크립트 자체는 수정하지 않는다 — 매 실행이 새 프로세스라 코드 변경은
다음 실행에 자동 반영된다(기존 PM2 cron 동작과 동일).

PM2 대비 추가되는 것:
  - 실행 이력: 매 실행을 job_run 테이블에 기록(관리자 워커 현황 페이지의 데이터 소스)
  - 실패 경보: 비정상 종료(exit≠0)·타임아웃 시 관리자 텔레그램 알림
  - 타임아웃 백스톱: 잡별 timeout 초과 시 프로세스 강제 종료

안전장치:
  - misfire grace: 스케줄러가 죽었다 살아나도 유예를 넘긴 지각 실행은 하지 않는다
    (PM2 가 지나간 cron 을 안 돌리는 것과 동일). catch-up 설계 잡만 유예를 길게 준다.
  - max_instances=1 + coalesce: 같은 잡의 중복/누적 실행 방지.
  - 자금 경로(trading 워커)는 이 스케줄러가 관리하지 않는다 — PM2 잔류(단계적 이관 원칙).

수동 실행:  uv run workers/scheduler.py --once <잡이름>   (성공 시 exit 0)
잡 목록:    uv run workers/scheduler.py --list
"""
import argparse
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from core.logging_setup import setup_logging
from core.notifications import send_job_alert
from core.repository import job_run

setup_logging()
logger = logging.getLogger("Scheduler")

JONGALAB_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = JONGALAB_DIR / "logs" / "jobs"
LOG_TAIL_CHARS = 2000       # job_run.log_tail 로 남길 로그 꼬리 길이
RETENTION_DAYS = 60         # job_run 보존 기간
TZ = "Asia/Seoul"


@dataclass(frozen=True)
class Job:
    """스케줄 잡 1개. cron 필드는 APScheduler CronTrigger 인자 그대로.

    주의: day_of_week 는 반드시 이름("mon-fri"/"sat"/"sun")으로 쓴다 —
    APScheduler 의 숫자 요일은 표준 cron(0=일)과 달라(0=월) 사고 나기 쉽다.
    """
    name: str                       # job_run.job_name (워커 스크립트명과 동일하게)
    cmd: list[str]                  # spawn 커맨드
    timeout: int                    # 초과 시 강제 종료(초)
    grace: int                      # misfire 유예(초) — 이걸 넘긴 지각 실행은 스킵
    minute: str = "0"
    hour: str = "*"
    day_of_week: str = "*"
    cwd: Path = field(default=JONGALAB_DIR)

    def trigger(self) -> CronTrigger:
        return CronTrigger(minute=self.minute, hour=self.hour,
                           day_of_week=self.day_of_week, timezone=TZ)


UV_RUN = ["uv", "run"]

# ── 잡 정의 (1단계: jongalab 저위험 관측/연구 잡 — 자금 경로 없음) ──
# 스케줄 변경·잡 추가는 이 목록만 수정하면 된다(스케줄러 재시작 필요 — 배포 훅이 수행).
JOBS = [
    # 15분 주기 콘텐츠 수집. LLM 분석 포함이라 여유 있게 14분 컷(다음 주기 직전).
    Job("youtube_collector", UV_RUN + ["workers/youtube_collector.py"],
        timeout=840, grace=300, minute="*/15"),
    # 매일 04:00 오래된 콘텐츠/뉴스 정리. 하루 안이면 언제 돌아도 무방 → 유예 6h.
    Job("cleanup_content", UV_RUN + ["workers/cleanup_content.py"],
        timeout=600, grace=21600, minute="0", hour="4"),
    # 일요일 07:30 상장종목 시딩. 주 1회라 유예 6h.
    Job("news_ticker_seed", UV_RUN + ["workers/news_ticker_seed.py"],
        timeout=900, grace=21600, minute="30", hour="7", day_of_week="sun"),
    # 평일 09:30 결과 라벨 백필. catch-up 설계(미완결분 익일 재시도) → 유예 6h.
    Job("outcome_backfill", UV_RUN + ["workers/outcome_backfill.py"],
        timeout=1200, grace=21600, minute="30", hour="9", day_of_week="mon-fri"),
    # 평일 09:40 Edge Ledger 채점. catch-up 설계 → 유예 6h.
    Job("rule_evaluator", UV_RUN + ["workers/rule_evaluator.py"],
        timeout=1200, grace=21600, minute="40", hour="9", day_of_week="mon-fri"),
    # 평일 08:20~20:50 매 30분 DART 공시 수집(:20/:50 — closing_bet :00/:30 직전 갱신).
    # 멱등 적재라 지각 실행도 무해하지만, 늦게 도는 건 의미가 없어 유예 10분.
    Job("disclosure_collector", UV_RUN + ["workers/disclosure_collector.py"],
        timeout=600, grace=600, minute="20,50", hour="8-20", day_of_week="mon-fri"),
    # 평일 17:50 시간외/리스크 라벨. ka10087 이 16~18시에만 살아있어 유예 5분(18시 넘기면 무의미).
    Job("after_hours_labels", UV_RUN + ["workers/after_hours_labels.py"],
        timeout=900, grace=300, minute="50", hour="17", day_of_week="mon-fri"),
    # 토요일 08:00 주간 가중치 튜너(GPT 호출 포함). 유예 6h.
    Job("weight_tuner", UV_RUN + ["workers/weight_tuner.py"],
        timeout=2400, grace=21600, minute="0", hour="8", day_of_week="sat"),
    # 월요일 08:20 거시 이벤트 캘린더 고갈 체크(3주 내 바닥나면 exit 1 → 경보). 유예 6h.
    Job("macro_event_check", UV_RUN + ["workers/macro_event_check.py"],
        timeout=120, grace=21600, minute="20", hour="8", day_of_week="mon"),
]


def _read_tail(log_path: Path, offset: int) -> str:
    """이번 실행 구간(offset 이후)의 로그 꼬리를 읽는다."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            text = f.read()
        return text[-LOG_TAIL_CHARS:].strip()
    except OSError:
        return ""


def run_job(job: Job) -> str:
    """잡 1회 실행: job_run 기록 + 로그 파일 append + 실패 경보. 반환: 최종 status."""
    scheduled_at = datetime.now()
    log_path = LOG_DIR / f"{job.name}.log"

    try:
        run_id = job_run.start_run(job.name, scheduled_at)
    except Exception as e:
        # 이력 DB 장애가 잡 실행 자체를 막으면 안 된다 — 기록 없이 실행만 계속.
        logger.error("job_run 기록 실패(실행은 계속): %s — %s", job.name, e)
        run_id = None

    logger.info("▶ %s 시작 (timeout %ds)", job.name, job.timeout)
    status, exit_code = "fail", None
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n===== {scheduled_at:%Y-%m-%d %H:%M:%S} {job.name} =====\n")
        f.flush()
        offset = f.tell()
        try:
            # start_new_session: uv run 이 낳는 python 자식까지 한 프로세스 그룹으로 묶는다
            # (타임아웃 kill 시 그룹 전체를 죽여야 고아 워커가 남지 않는다).
            proc = subprocess.Popen(
                job.cmd, cwd=job.cwd, stdout=f, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                start_new_session=True,
            )
        except OSError as e:
            f.write(f"[scheduler] spawn 실패: {e}\n")
            _finalize(job, run_id, "fail", None, f"spawn 실패: {e}")
            return "fail"
        try:
            exit_code = proc.wait(timeout=job.timeout)
            status = "success" if exit_code == 0 else "fail"
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)   # uv 부모만 죽이면 python 자식이 고아로 남는다
            except ProcessLookupError:
                pass
            proc.wait()
            status = "timeout"
            f.write(f"[scheduler] {job.timeout}s 타임아웃 — 프로세스 그룹 강제 종료\n")

    tail = _read_tail(log_path, offset)
    _finalize(job, run_id, status, exit_code, tail)
    return status


def _finalize(job: Job, run_id: int | None, status: str,
              exit_code: int | None, tail: str) -> None:
    if run_id is not None:
        try:
            job_run.finish_run(run_id, status, exit_code, tail)
        except Exception as e:
            logger.error("job_run 종료 기록 실패: %s — %s", job.name, e)
    if status == "success":
        logger.info("✔ %s 완료", job.name)
    else:
        logger.error("✖ %s %s (exit=%s)", job.name, status, exit_code)
        send_job_alert(job.name, status, exit_code, tail)


def main() -> int:
    parser = argparse.ArgumentParser(description="통합 잡 스케줄러")
    parser.add_argument("--list", action="store_true", help="잡 목록과 다음 실행 시각 출력 후 종료")
    parser.add_argument("--once", metavar="JOB", help="지정 잡을 즉시 1회 실행 후 종료")
    args = parser.parse_args()

    if args.list:
        now = datetime.now().astimezone()
        for job in JOBS:
            nxt = job.trigger().get_next_fire_time(None, now)
            print(f"{job.name:22s} next={nxt:%Y-%m-%d %H:%M}  timeout={job.timeout}s grace={job.grace}s")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.once:
        job = next((j for j in JOBS if j.name == args.once), None)
        if not job:
            print(f"알 수 없는 잡: {args.once} (--list 로 확인)", file=sys.stderr)
            return 2
        return 0 if run_job(job) == "success" else 1

    # 시작 정리: 이전 프로세스가 남긴 running 행 마감 + 보존 기간 지난 이력 삭제
    try:
        swept = job_run.sweep_stale_running()
        pruned = job_run.delete_old_runs(RETENTION_DAYS)
        if swept or pruned:
            logger.info("시작 정리: running→aborted %d건, %d일 초과 삭제 %d건",
                        swept, RETENTION_DAYS, pruned)
    except Exception as e:
        logger.error("시작 정리 실패(계속 진행): %s", e)

    scheduler = BlockingScheduler(timezone=TZ)
    for job in JOBS:
        scheduler.add_job(
            run_job, job.trigger(), args=[job], id=job.name, name=job.name,
            misfire_grace_time=job.grace, coalesce=True, max_instances=1,
        )
    logger.info("스케줄러 시작 — 잡 %d개 등록: %s", len(JOBS), ", ".join(j.name for j in JOBS))
    scheduler.start()   # SIGINT/SIGTERM 까지 블로킹
    return 0


if __name__ == "__main__":
    sys.exit(main())
