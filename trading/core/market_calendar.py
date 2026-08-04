"""거래일(개장일) 판별 유틸 — jongalab/core/market_calendar.py 의 최소 복제.

trading 워커(signal_executor, monitor, settle 등)는 PM2 cron(평일)으로 돌지만
평일 공휴일에는 그대로 실행되어 휴장일 주문 시도(전건 거부)·기록 오염이 생긴다
(2026-07-17 제헌절 사고). 진입부에서 `exit_if_not_trading_day()` 로 막는다.

KRX 개장 여부는 `exchange_calendars` 의 'XKRX' 달력으로 판단한다(오프라인·
선행조회 가능). 달력 로드/조회에 실패하면 주말 여부만으로 안전하게 폴백한다.
"""
import sys
import logging
from datetime import date, datetime, time, timedelta

logger = logging.getLogger(__name__)

_XKRX = "XKRX"

# XKRX 달력 데이터에 아직 반영되지 않은 휴장일 수동 오버라이드.
# jongalab/core/market_calendar.py 에 동일 목록이 있다 — 수정 시 양쪽을 함께 갱신할 것.
EXTRA_HOLIDAYS: set[date] = {
    date(2026, 7, 17),  # 제헌절 (2026-07-17 휴장 확인 — 달력 4.13.2 미반영)
}


def is_trading_day(dt: datetime | None = None) -> bool:
    """KRX 개장일이면 True, 휴장일(주말·공휴일 등)이면 False.

    `EXTRA_HOLIDAYS` 수동 오버라이드를 먼저 보고, 그 외에는 XKRX 달력으로
    판단한다. 라이브러리 로드/조회 실패 시 주말(토/일) 여부로만 폴백 판단한다.
    """
    d = dt or datetime.now()
    if d.date() in EXTRA_HOLIDAYS:
        return False
    is_weekday = d.weekday() < 5  # 0=월 ... 4=금, 5=토, 6=일
    try:
        import exchange_calendars as xcals
        import pandas as pd

        cal = xcals.get_calendar(_XKRX)
        return bool(cal.is_session(pd.Timestamp(d.date())))
    except Exception as e:  # 달력 사용 불가 → 최소한 주말은 거른다
        logger.warning("XKRX 거래소 달력 조회 실패(%s) — 주말 여부로만 판단합니다.", e)
        return is_weekday


def next_trading_day(d: date) -> date:
    """d 직후 거래일 — '이 매수분을 언제 파는가'(익일 시가 청산일) 판정에 쓴다.

    최대 14일까지만 앞으로 본다(연휴가 아무리 길어도 그 안에 개장일이 있다) —
    달력 조회가 통째로 실패해 무한 루프가 되는 것을 막는 상한이다.
    jongalab/core/market_calendar.py 에 동일 함수가 있다(최소 복제 유지).
    """
    for fwd in range(1, 15):
        cand = d + timedelta(days=fwd)
        if is_trading_day(datetime.combine(cand, time.min)):
            return cand
    return d + timedelta(days=1)


def exit_if_not_trading_day() -> None:
    """휴장일이면 프로세스를 즉시 정상 종료(exit 0)한다.

    cron 스케줄(`* * * 1-5`)은 평일만 돌지만 평일 공휴일·pm2 restart 즉시 실행은
    막지 못하므로, 모든 워커 진입부에서 한 번 더 막는다.
    """
    if not is_trading_day():
        logger.info("휴장일(주말·공휴일 등) — 워커를 실행하지 않고 종료합니다.")
        sys.exit(0)
