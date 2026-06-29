"""미실행 감시 워커 (dead-man's switch).

핵심 손실 방지 워커(monitor·settle)가 '오늘 정상 완료' 마커(audit_log: worker_done)를
남겼는지 확인하고, 누락이면 관리자에게 텔레그램 경보를 보낸다.

배경: monitor(하드손절/트레일링)·settle(시초가 청산)이 cron 미발동·크래시로 안 돌면
손절 미작동·오버나잇 보유로 직접 손실이 난다. 이 둘은 실패해도 스스로 알리지 않으므로
(거래가 없으면 조용히 끝남) 외부에서 '돌았는지'를 확인하는 안전망이 필요하다.

판정은 완료 마커 유무만 본다(포지션/신호 상태를 추론하지 않음) → 무거래일에도 오경보 없음.
모든 핵심 워커의 가동 구간이 끝난 뒤(평일 09:35) 한 번 실행한다.
"""
import sys
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.repository import audit_log
from core.notifications import notify_admin

setup_logging()
logger = logging.getLogger("Watchdog")

# 감시 대상: (완료 마커 이름, 마감 시각 (시,분), 설명). 마감 시각까지 완료돼야 한다.
# 새 워커를 감시에 추가하려면 여기에 한 줄(가동 구간 종료 시각 기준)만 더한다.
CRITICAL_WORKERS = [
    ("settle:nxt",      (8, 5),  "NXT 시초가 갭 청산(절반 매도)"),
    ("settle:krx_open", (9, 5),  "KRX 개장 비-NXT 갭 청산(절반 매도)"),
    ("settle:krx",      (9, 28), "KRX 데드라인 잔량 청산"),
    ("monitor",         (9, 30), "하드손절/트레일링 스탑 감시"),
]


def _minutes(hm) -> int:
    return hm[0] * 60 + hm[1]


def missing_workers(now_hm, done, critical=CRITICAL_WORKERS) -> list:
    """마감 시각이 지난 핵심 워커 중 완료 마커가 없는 것 목록.

    now_hm: 현재 (시,분)  ·  done: 오늘 완료 마커 이름 집합  →  [(name, by, desc), ...]
    순수함수(테스트 용이) — DB·시계에 의존하지 않는다.
    """
    now_m = _minutes(now_hm)
    return [(name, by, desc) for (name, by, desc) in critical
            if now_m >= _minutes(by) and name not in done]


def main() -> int:
    now = datetime.now()
    # 실행 윈도우 가드: 평일에만(주말·pm2 즉시 오실행 방지).
    if now.weekday() >= 5:
        logger.info("주말 — 감시 스킵 (%s)", now.strftime("%a %H:%M"))
        return 0

    date_dash = now.strftime("%Y-%m-%d")
    try:
        done = audit_log.workers_done_today(date_dash)
    except Exception as e:
        # 마커를 못 읽으면 감시 자체가 무력화된 것 → 안전상 경보.
        logger.error("완료 마커 조회 실패 — 안전상 경보: %s", e)
        notify_admin(f"🚨 *watchdog 오류* {now:%Y-%m-%d %H:%M}\n완료 마커 조회 실패: `{e}`")
        return 1

    missing = missing_workers((now.hour, now.minute), done)
    if not missing:
        logger.info("핵심 워커 정상 완료 확인 — 이상 없음 (done=%s)", sorted(done))
        return 0

    lines = "\n".join(
        f"• `{name}` — {desc} (마감 {by[0]:02d}:{by[1]:02d})" for name, by, desc in missing
    )
    msg = (
        f"🚨 *자동매매 워커 미실행 감지* {now:%Y-%m-%d %H:%M}\n"
        f"아래 워커의 완료 마커가 없습니다. 손절/청산 미작동 위험 — "
        f"PM2 로그·포지션을 즉시 확인하세요.\n{lines}"
    )
    logger.error("미실행 워커 감지: %s", [m[0] for m in missing])
    notify_admin(msg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
