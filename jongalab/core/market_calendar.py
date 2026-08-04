"""거래일(개장일) 판별 유틸.

평일 전용 워커(gap_check, closing_bet)가 휴장일(주말·공휴일·
대체공휴일·근로자의날·연말휴장 등)에 실행될 때 — 예: pm2 restart 로 cron 과
무관하게 즉시 기동 — 곧바로 종료하도록 돕는다.

KRX 개장 여부는 `exchange_calendars` 의 'XKRX' 달력으로 판단한다(오프라인·
선행조회 가능). 달력 로드/조회에 실패하면 주말 여부만으로 안전하게 폴백한다.
"""
import sys
import logging
from datetime import date, datetime, time, timedelta

logger = logging.getLogger(__name__)

_XKRX = "XKRX"

# XKRX 달력 데이터에 아직 반영되지 않은 휴장일 수동 오버라이드.
# 새로 지정된 공휴일(예: 제헌절 재지정)은 exchange_calendars 릴리스가 따라오지
# 못하므로 여기 먼저 추가한다. trading/core/market_calendar.py 에 동일 목록이
# 복제되어 있다 — 수정 시 양쪽을 함께 갱신할 것.
EXTRA_HOLIDAYS: set[date] = {
    date(2026, 7, 17),  # 제헌절 (2026-07-17 휴장 확인 — 달력 4.13.2 미반영)
}

# EXTRA_HOLIDAYS 의 표시용 한글 이름(캘린더 라벨). 위 목록과 함께 갱신할 것.
EXTRA_HOLIDAY_NAMES: dict[date, str] = {
    date(2026, 7, 17): "제헌절",
}

# exchange_calendars 가 주는 영문 휴일명 → 한글 라벨. 앞에서부터 첫 부분일치를 쓴다
# (예: "Seollal (New Year's Day by the lunar) (-1 day)" → 설날). "New Year" 는
# 설날 문자열에도 들어가므로 반드시 Seollal 뒤에 둔다.
_HOLIDAY_KO: list[tuple[str, str]] = [
    ("Seollal", "설날"),
    ("Chuseok", "추석"),
    ("Independence Movement", "삼일절"),
    ("Liberation", "광복절"),
    ("Foundation", "개천절"),
    ("Hangul", "한글날"),
    ("Memorial", "현충일"),
    ("Children", "어린이날"),
    ("Buddha", "부처님오신날"),
    ("Labor", "근로자의 날"),
    ("Christmas", "성탄절"),
    ("End of Year", "연말 휴장"),
    ("New Year", "신정"),
]


def _translate_holiday(eng: str) -> str:
    for key, ko in _HOLIDAY_KO:
        if key in eng:
            return ko
    return "휴장일"


def holidays_in_month(month: str) -> list[dict]:
    """month(YYYY-MM)에서 개장하지 않는 평일(공휴일·대체공휴일·근로자의날·연말휴장
    등)을 [{"date": "YYYY-MM-DD", "name": 한글}] 로 돌려준다.

    캘린더는 평일만 그리므로 주말은 제외한다. 휴장 판정은 XKRX 세션 여부(권위)와
    EXTRA_HOLIDAYS 오버라이드로 하고, 이름은 exchange_calendars 영문명을 한글로
    옮긴다(대체공휴일 등 이름 없는 날은 "대체공휴일"/"휴장일"). 달력 조회 실패 시
    EXTRA_HOLIDAYS 만으로 폴백한다.
    """
    import calendar as _cal

    parts = month.split("-")
    if len(parts) != 2:
        return []
    year, mon = int(parts[0]), int(parts[1])
    days = _cal.monthrange(year, mon)[1]

    names: dict[date, str] = {}
    is_session = None
    try:
        import exchange_calendars as xcals
        import pandas as pd

        cal = xcals.get_calendar(_XKRX)
        is_session = lambda d: bool(cal.is_session(pd.Timestamp(d)))  # noqa: E731
        series = cal.regular_holidays.holidays(
            pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31"), return_name=True
        )
        for ts, eng in series.items():
            names[ts.date()] = _translate_holiday(str(eng))
        for ts in cal.adhoc_holidays:  # 대체공휴일 등 (이름 없음)
            t = pd.Timestamp(ts)
            if t.year == year:
                names.setdefault(t.date(), "대체공휴일")
    except Exception as e:
        logger.warning("XKRX 달력 조회 실패(%s) — EXTRA_HOLIDAYS 만으로 휴일 표시.", e)

    out: list[dict] = []
    for day in range(1, days + 1):
        d = date(year, mon, day)
        if d.weekday() >= 5:  # 주말은 캘린더에 없음
            continue
        closed = d in EXTRA_HOLIDAYS or (is_session is not None and not is_session(d))
        if not closed:
            continue
        name = EXTRA_HOLIDAY_NAMES.get(d) or names.get(d) or "휴장일"
        out.append({"date": d.isoformat(), "name": name})
    return out


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


def prev_trading_day(d: date) -> date:
    """d 직전 거래일. 권리락일 = 신주배정기준일 직전 영업일 계산에 쓴다(sql/48).

    최대 14일까지만 뒤로 본다(연휴가 아무리 길어도 그 안에 개장일이 있다) —
    달력 조회가 통째로 실패해 무한 루프가 되는 것을 막는 상한이다.
    """
    for back in range(1, 15):
        cand = d - timedelta(days=back)
        if is_trading_day(datetime.combine(cand, time.min)):
            return cand
    return d - timedelta(days=1)


def next_trading_day(d: date) -> date:
    """d 직후 거래일. '익일 시가 청산'이 실제로 언제인지 판정할 때 쓴다."""
    for fwd in range(1, 15):
        cand = d + timedelta(days=fwd)
        if is_trading_day(datetime.combine(cand, time.min)):
            return cand
    return d + timedelta(days=1)


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
