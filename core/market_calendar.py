"""거래일(개장일) 판별 유틸.

평일 전용 워커(daily_digest, gap_check, closing_bet)가 휴장일(주말·공휴일·
대체공휴일·근로자의날·연말휴장 등)에 실행될 때 — 예: pm2 restart 로 cron 과
무관하게 즉시 기동 — 곧바로 종료하도록 돕는다.

KRX 개장 여부는 `exchange_calendars` 의 'XKRX' 달력으로 판단한다(오프라인·
선행조회 가능). 달력 로드/조회에 실패하면 주말 여부만으로 안전하게 폴백한다.
"""
import sys
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_XKRX = "XKRX"


def is_trading_day(dt: datetime | None = None) -> bool:
    """KRX 개장일이면 True, 휴장일(주말·공휴일 등)이면 False.

    XKRX 달력으로 정확히 판단하되, 라이브러리 로드/조회 실패 시
    주말(토/일) 여부로만 폴백 판단한다.
    """
    d = dt or datetime.now()
    is_weekday = d.weekday() < 5  # 0=월 ... 4=금, 5=토, 6=일
    try:
        import exchange_calendars as xcals
        import pandas as pd

        cal = xcals.get_calendar(_XKRX)
        return bool(cal.is_session(pd.Timestamp(d.date())))
    except Exception as e:  # 달력 사용 불가 → 최소한 주말은 거른다
        logger.warning("XKRX 거래소 달력 조회 실패(%s) — 주말 여부로만 판단합니다.", e)
        return is_weekday


def exit_if_not_trading_day() -> None:
    """휴장일이면 프로세스를 즉시 정상 종료(exit 0)한다.

    cron 스케줄(`* * * 1-5`)은 평일만 돌지만 pm2 restart 는 스케줄을 무시하고
    즉시 실행하므로, 평일 공휴일을 포함한 모든 휴장일을 진입부에서 한 번 더 막는다.
    """
    if not is_trading_day():
        logger.info("휴장일(주말·공휴일 등) — 워커를 실행하지 않고 종료합니다.")
        sys.exit(0)


def exit_if_outside_window(start_hour: int, end_hour: int, *, dt: datetime | None = None) -> None:
    """휴장일이거나 운영 시간대(시 단위) 밖이면 프로세스를 즉시 정상 종료(exit 0)한다.

    `exit_if_not_trading_day()` 와 동일하게 거래일(주말·공휴일 포함)을 먼저 막고,
    추가로 `start_hour <= 현재 시각(시) <= end_hour`(양끝 포함) 범위만 통과시킨다.
    cron 스케줄과 무관하게 pm2 restart/start 로 즉시 기동될 때, 의도한 운영
    시간대 밖(예: 새벽) 실행을 한 번 더 차단하기 위함이다.
    """
    d = dt or datetime.now()
    if not is_trading_day(d):
        logger.info("휴장일(주말·공휴일 등) — 워커를 실행하지 않고 종료합니다.")
        sys.exit(0)
    if not (start_hour <= d.hour <= end_hour):
        logger.info(
            "운영 시간대(%02d~%02d시) 밖(현재 %02d:%02d) — 워커를 실행하지 않고 종료합니다.",
            start_hour, end_hour, d.hour, d.minute,
        )
        sys.exit(0)
