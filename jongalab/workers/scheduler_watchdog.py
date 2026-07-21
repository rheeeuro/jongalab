#!/usr/bin/env python
"""jongalab-scheduler 워치독 — 스케줄러 프로세스가 죽으면 자동 재기동 + 관리자 알림.

배경: jongalab-scheduler 는 상시 워커라, 죽으면 거기 등록된 저위험 cron 잡 8개가
함께 멈춘다. 그런데 스케줄러 자신이 죽은 상태에서는 실패 알림(send_job_alert)을
보낼 주체가 없다 — 즉 "스케줄러 다운"은 스케줄러의 사각지대다.

2026-07-21 PM2 데몬이 06:12 통째로 재시작(pm2 update 류)된 뒤 대부분 앱은 resurrect
되었으나 jongalab-scheduler 만 되살아나지 못해 3시간여 방치된 사건이 있었다. 그 대응으로
스케줄러 **밖에서** 도는 이 워커가 pm2 상태를 주기적으로 확인해 정지 시 자동 복구하고
관리자에게 경보한다.

- 실행: ecosystem.config.js 의 cron 워커로 5분마다 spawn(autorestart:false).
- 판정: status 가 online/launching 이 아니면(=stopped/errored/미등록) 재기동 대상.
- 알림: 기존 send_job_alert 를 job_name="jongalab-scheduler" 로 재사용(관리자 텔레그램).
"""
import json
import logging
import subprocess
import sys

from core.logging_setup import setup_logging
from core.notifications import send_job_alert

setup_logging()
logger = logging.getLogger("SchedulerWatchdog")

APP = "jongalab-scheduler"
ECOSYSTEM = "/home/euro/dev/jongalab/ecosystem.config.js"
HEALTHY = ("online", "launching")  # 재기동이 필요 없는 상태


def pm2_status(app: str) -> str | None:
    """pm2 jlist 에서 app 의 상태 문자열을 반환. pm2 에 아예 없으면 None."""
    out = subprocess.run(
        ["pm2", "jlist"], capture_output=True, text=True, timeout=30
    )
    for p in json.loads(out.stdout or "[]"):
        if p.get("name") == app:
            return p.get("pm2_env", {}).get("status")
    return None


def main() -> int:
    status = pm2_status(APP)
    if status in HEALTHY:
        logger.info(f"{APP} status={status} — 정상")
        return 0

    logger.warning(f"{APP} status={status} — 자동 재기동 시도")
    if status is None:
        # pm2 목록에서 아예 사라진 경우: ecosystem 정의로 재등록
        cmd = ["pm2", "start", ECOSYSTEM, "--only", APP]
    else:
        cmd = ["pm2", "start", APP]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    new = pm2_status(APP)
    ok = new in HEALTHY
    logger.info(f"재기동 결과: {status} -> {new} (rc={proc.returncode})")
    send_job_alert(
        job_name=APP,
        status=f"프로세스 정지 감지({status}) → 자동 재기동 {'성공' if ok else '실패'}",
        exit_code=None,
        log_tail=((proc.stdout or "") + (proc.stderr or "")).strip(),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
