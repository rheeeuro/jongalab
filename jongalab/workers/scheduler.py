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
    # 평일 08:00~20:30 매 30분 DART 공시 수집(:00/:30 — closing_bet :10/:40 직전 10분 갱신).
    # 멱등 적재라 지각 실행도 무해하지만, 늦게 도는 건 의미가 없어 유예 10분.
    Job("disclosure_collector", UV_RUN + ["workers/disclosure_collector.py"],
        timeout=600, grace=600, minute="0,30", hour="8-20", day_of_week="mon-fri"),
    # 매일 08:25~20:55 매 30분 네이버 증권 뉴스 수집(:25/:55 — closing_bet :10/:40 직전 15분 및
    # disclosure_collector :00/:30 과 어긋나게). 멱등 적재라 지각 실행도 무해하지만 늦게 도는 건
    # 의미가 없어 유예 10분. 실측 38종목 14초라 타임아웃은 넉넉히 5분.
    # 휴장일도 도는 이유: 당일 기사만 적재하는 구조라 연휴 재료를 그날 안 담으면 영영 못 담고,
    # 그러면 재개장일 선정 시점에 라벨이 빈다(근거: docs/history/news-pipeline.md).
    Job("naver_news_collector", UV_RUN + ["workers/naver_news_collector.py"],
        timeout=300, grace=600, minute="25,55", hour="8-20"),
    # 매일 08:05~20:35 매 30분 증권 섹션 뉴스 수집(뉴스 탭 표시용, :05/:35 — 위 세 잡과 어긋나게).
    # 멱등 적재라 지각 실행도 무해하지만 늦게 도는 건 의미가 없어 유예 10분. 실측 2~3페이지
    # ×20건이라 한 사이클 5초 안쪽 — 타임아웃은 상한(8페이지) 기준으로 넉넉히 3분.
    Job("sec_news_collector", UV_RUN + ["workers/sec_news_collector.py"],
        timeout=180, grace=600, minute="5,35", hour="8-20"),
    # 평일 17:50 시간외/리스크 라벨. ka10087 이 16~18시에만 살아있어 유예 5분(18시 넘기면 무의미).
    Job("after_hours_labels", UV_RUN + ["workers/after_hours_labels.py"],
        timeout=900, grace=300, minute="50", hour="17", day_of_week="mon-fri"),
    # 평일 14:30 리스크 라벨만 먼저 — KRX 매수(15:20)·NXT 매수(19:50) 선정 회차가 공매도 비중·
    # 신용잔고율·대차를 보게 한다. 값은 T-1 확정치라 17:50 회차와 **같다**(수집 시각만 앞당김).
    # 유예 20분 — 매수 창을 넘겨 지각 실행하는 건 이 잡의 목적이 아니라 스킵이 맞다
    # (sector_news_labeler_pre_krx 와 같은 규율). 17:50 회차가 어차피 같은 값을 다시 채운다.
    Job("after_hours_risk_pre_buy",
        UV_RUN + ["workers/after_hours_labels.py", "--risk-only"],
        timeout=600, grace=1200, minute="30", hour="14", day_of_week="mon-fri"),
    # 평일 14:30 시장 스냅샷(슬롯 1430) — KRX 종가매수(15:20) 축.
    Job("market_snapshot_pre_buy",
        UV_RUN + ["workers/gap_check.py", "--market-snap"],
        timeout=300, grace=1200, minute="30", hour="14", day_of_week="mon-fri"),
    # 평일 19:35 시장 스냅샷(슬롯 1935) — NXT 매수 회차(closing_bet 19:40)가 읽는 축.
    # 야간세션이 18:00 에 시작하므로 **야간선물이 살아있는 유일한 선정 슬롯**이다(1430 에선
    # 전일 야간 종가다). 유예 4분 — 19:40 회차를 넘겨 지각 실행하면 선정이 못 읽으므로 스킵.
    Job("market_snapshot_pre_nxt",
        UV_RUN + ["workers/gap_check.py", "--market-snap-nxt"],
        timeout=240, grace=240, minute="35", hour="19", day_of_week="mon-fri"),
    # 토요일 08:00 주간 가중치 튜너(GPT 호출 포함). 유예 6h.
    Job("weight_tuner", UV_RUN + ["workers/weight_tuner.py"],
        timeout=2400, grace=21600, minute="0", hour="8", day_of_week="sat"),
    # 월요일 08:20 거시 이벤트 캘린더 고갈 체크(3주 내 바닥나면 exit 1 → 경보). 유예 6h.
    Job("macro_event_check", UV_RUN + ["workers/macro_event_check.py"],
        timeout=120, grace=21600, minute="20", hour="8", day_of_week="mon"),
    # 매일 20:30 미매칭 뉴스 섹터·거시 라벨(관측 전용 표본 축적, LLM 벌크) — **백로그 소화**.
    # **매일**인 이유: 코퍼스는 주말에도 쌓이고(실측 토·일 각 800건) 밀리면 상한에 걸린다.
    # 하루 안이면 언제 돌아도 무방(라벨은 news_at 기준이라 실행 시각과 무관) → 유예 6h.
    Job("sector_news_labeler", UV_RUN + ["workers/sector_news_labeler.py"],
        timeout=1800, grace=21600, minute="30", hour="20"),
    # 평일 매수 직전 같은 라벨러를 **그날 00시 이후 전량** 한 번 더 — KRX(15:20)·NXT(19:50)
    # 판단 시점에 그날 거시·섹터 기사가 라벨을 갖고 있게 한다. 20:30 실행만 있으면 라벨이 항상
    # 매수 뒤에 생겨 뉴스 축을 검정조차 할 수 없다. 라벨은 여전히 관측 전용(시드·점수·veto 무영향).
    # 상한 1500 은 하루치(실측 1,700~2,000건 중 절반씩 두 회차)를 덮는 안전값이고, 포화하면
    # 워커가 경고를 남긴다 — 상한이 그날 전량을 자르면 뉴스 톤 축의 표본 정의가 조용히 바뀐다.
    # 유예 20분 — 매수 창을 넘겨 지각 실행하는 건 이 잡의 목적이 아니라 스킵이 맞다.
    # 두 잡으로 나눈 이유: cron 필드는 교차곱이라 hour="14,19"+minute="30,0" 이면 14:00·19:30
    # 까지 4번 돈다. 또 잡 이름이 APScheduler id 라 이름을 겹칠 수 없다.
    Job("sector_news_labeler_pre_krx",
        UV_RUN + ["workers/sector_news_labeler.py",
                  "--since-today", "--newest-first", "--limit", "1500"],
        timeout=900, grace=1200, minute="30", hour="14", day_of_week="mon-fri"),
    Job("sector_news_labeler_pre_nxt",
        UV_RUN + ["workers/sector_news_labeler.py",
                  "--since-today", "--newest-first", "--limit", "1500"],
        timeout=900, grace=1200, minute="0", hour="19", day_of_week="mon-fri"),
    # 매일 20:50 일간 변경사항 저널(GPT 요약 + 관리자 텔레그램). 집계 창이 날짜로 고정이라
    # 지각 실행해도 내용이 같다 → 유예는 자정을 넘기지 않는 선(3h)에서 넉넉히.
    Job("journal_daily", UV_RUN + ["workers/journal.py", "--mode", "daily"],
        timeout=600, grace=10800, minute="50", hour="20"),
    # 토요일 10:00 주간 저널 — 그 주 일간 파일(직전 토~금)을 재요약. 유예 6h.
    Job("journal_weekly", UV_RUN + ["workers/journal.py", "--mode", "weekly"],
        timeout=900, grace=21600, minute="0", hour="10", day_of_week="sat"),
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
