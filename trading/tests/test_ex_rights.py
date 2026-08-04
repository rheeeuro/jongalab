"""권리락 스킵 테스트 — 청산일 판정과 fail-open (DB·네트워크 없이 fake 로 검증).

핵심 보장:
  1. 스킵 기준일은 **다음 거래일**(= 이 매수분의 청산일)이다 — 오늘 권리락인 종목은 대상 아님
     (조정이 끝난 가격에 사서 다음날 파는 건 정상 거래다)
  2. 금요일 매수는 월요일이 청산일 — 주말을 건너뛴다
  3. 캘린더 조회가 실패하면 빈 dict = 미개입(매수 정상 진행). 이 게이트가 매수를 막지 않는다
"""
from datetime import date

from core import ex_rights
from core.market_calendar import next_trading_day


def test_next_trading_day_skips_weekend_and_holiday():
    # 2026-08-07 금 → 08-10 월 (주말 건너뜀)
    assert next_trading_day(date(2026, 8, 7)) == date(2026, 8, 10)
    assert next_trading_day(date(2026, 8, 4)) == date(2026, 8, 5)
    # EXTRA_HOLIDAYS 수동 오버라이드(제헌절 2026-07-17 금)도 건너뛴다 → 07-20 월
    assert next_trading_day(date(2026, 7, 16)) == date(2026, 7, 20)


def test_uses_next_session_not_today(monkeypatch):
    """오늘 권리락인 종목은 스킵 대상이 아니다 — 조회 날짜가 다음 거래일이어야 한다."""
    asked = []

    def fake_fetch(on_date):
        asked.append(on_date)
        return {"196170": {"ratio": 0.3}} if on_date == date(2026, 8, 5) else {}

    monkeypatch.setattr(ex_rights, "fetch_ex_rights_on", fake_fetch)

    # 8/4 매수 → 청산 8/5 = 권리락일 → 스킵 대상
    assert "196170" in ex_rights.get_next_session_ex_rights(date(2026, 8, 4))
    # 8/5(권리락 당일) 매수 → 청산 8/6 → 이미 조정 끝, 스킵 대상 아님
    assert ex_rights.get_next_session_ex_rights(date(2026, 8, 5)) == {}
    assert asked == [date(2026, 8, 5), date(2026, 8, 6)]


def test_fetch_failure_is_no_intervention(monkeypatch):
    """조회 예외는 빈 dict — 매수를 통째로 막는 실패 모드가 없어야 한다."""
    def boom(on_date):
        raise RuntimeError("jongalab DB 연결 실패")

    monkeypatch.setattr(ex_rights, "fetch_ex_rights_on", boom)
    assert ex_rights.get_next_session_ex_rights(date(2026, 8, 4)) == {}
