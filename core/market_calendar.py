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
