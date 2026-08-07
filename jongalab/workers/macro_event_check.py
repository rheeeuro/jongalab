"""macro_event 캘린더 고갈 체크 — 시드가 3주 내로 바닥나면 실패(exit 1)로 스케줄러 경보를 태운다.

거시 이벤트 캘린더(FOMC·CPI·고용 등)는 연 단위 수동 시드다(sql/18. migrate_macro_event.sql).
시드를 잊으면 trading macro_gate 가 '이벤트 없음'으로 오판해 조용히 무력화되므로,
마지막 이벤트가 HORIZON_DAYS 안이면 비정상 종료해 send_job_alert(텔레그램) 경보를 받는다.
연말마다 다음 해 일정(연준/BLS/한은 발표)을 같은 마이그레이션 파일 방식으로 추가하면 된다.

감시 대상은 **severity>=3**(실제로 시드를 감액하는 계열)이다 — 관찰 전용 sev2(PPI·해외 실적)가
더 멀리 시드돼 있어도 sev3 고갈을 가리지 않게. sev2 는 감액에 쓰이지 않으므로 고갈해도 무해하다.
"""
import logging
import sys
from datetime import datetime, timedelta

from core.logging_setup import setup_logging
from core.repository import macro_event

setup_logging()
logger = logging.getLogger("MacroEventCheck")

HORIZON_DAYS = 21


def main() -> int:
    last = macro_event.last_event_time()
    deadline = datetime.now() + timedelta(days=HORIZON_DAYS)
    if last is None:
        logger.error("macro_event 가 비어 있음 — 캘린더 시드 필요")
        return 1
    if last < deadline:
        logger.error("macro_event 고갈 임박 — 마지막 이벤트 %s (< %d일). 다음 분기/연도 일정을 시드하세요.",
                     last, HORIZON_DAYS)
        return 1
    logger.info("macro_event 정상 — 마지막 이벤트 %s", last)
    return 0


if __name__ == "__main__":
    sys.exit(main())
