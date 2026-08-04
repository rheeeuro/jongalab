"""권리락 예정일 파생 계약 테스트 (순수 로직, DB·네트워크 무의존).

권리락일을 틀리면 두 방향으로 손해다 — 늦으면 기계적 -23% 를 안고 오버나이트하고,
과잉이면 멀쩡한 종목의 매수 기회를 버린다. 그래서 파싱과 날짜 파생을 실측값으로 고정한다.
"""
from datetime import date

from core.dart_client import _parse_kdate, _parse_ratio
from core.market_calendar import next_trading_day, prev_trading_day


def test_parse_kdate_handles_dart_format():
    assert _parse_kdate("2026년 08월 06일") == "2026-08-06"
    assert _parse_kdate("2026.08.06") == "2026-08-06"
    # 미정·결측은 None (호출부가 그 종목을 건너뛴다)
    assert _parse_kdate("-") is None
    assert _parse_kdate("") is None
    assert _parse_kdate(None) is None


def test_parse_ratio():
    assert _parse_ratio("0.3") == 0.3
    assert _parse_ratio("1") == 1.0
    assert _parse_ratio("1,000") == 1000.0
    assert _parse_ratio("-") is None
    assert _parse_ratio(None) is None


def test_ex_rights_date_is_prev_trading_day_of_record_date():
    """권리락일 = 신주배정기준일 직전 영업일 — 2026-08-04 DART 실측 3건으로 고정."""
    # 알테오젠: 기준일 8/6(목) → 권리락 8/5(수)
    assert prev_trading_day(date(2026, 8, 6)) == date(2026, 8, 5)
    # 유진테크놀로지: 기준일 7/30(목) → 권리락 7/29(수)
    assert prev_trading_day(date(2026, 7, 30)) == date(2026, 7, 29)
    # RF머트리얼즈: 기준일 7/27(월) → 권리락 7/24(금). 주말을 건너뛴다
    assert prev_trading_day(date(2026, 7, 27)) == date(2026, 7, 24)


def test_prev_trading_day_skips_extra_holiday():
    """EXTRA_HOLIDAYS 수동 오버라이드(제헌절 2026-07-17 금)도 건너뛴다."""
    assert prev_trading_day(date(2026, 7, 20)) == date(2026, 7, 16)


def test_next_trading_day_mirrors_trading_side():
    """trading/core/market_calendar 의 동일 함수와 같은 결과여야 한다(최소 복제)."""
    assert next_trading_day(date(2026, 8, 7)) == date(2026, 8, 10)
    assert next_trading_day(date(2026, 7, 16)) == date(2026, 7, 20)
