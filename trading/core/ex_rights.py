"""권리락 스킵 — jongalab 권리락 예정일 캘린더(`ex_rights_schedule`, sql/48)를 읽기 전용 조회.

[왜]
종가베팅은 '오늘 종가 매수 → 익일 시가 매도'다. **익일이 권리락일이면** 기준가가 배정비율만큼
기계적으로 낮아져(무상증자 1주당 0.3주 → -23%) 그 폭이 그대로 실현손실로 찍힌다. 공짜 신주는
신주 상장일(보통 3주 뒤)에 들어오고 1주만 산 경우엔 단수주라 현금이므로, 그 자리에서 상계되지
않는다. 검증된 엣지(종가→익일시가)와 성격이 다른 거래이므로 **아예 매수하지 않는다**.
  2026-08-04 알테오젠(1등) 실사례: 종가 346,500 → 익일 기준가 267,000. 1주 매수 시 -79,500원
  확정, 보전분 8만원은 8/26 입금. 근거·판정 규칙은 sql/48 주석.

[경계] news_veto·macro_gate 와 같은 cross-DB 패턴 — jongalab 이 판정(캘린더)을 적재하고
여기는 읽기만 한다. 평단·손절선 같은 자금 상태는 건드리지 않는다(가격 보정이 아니라 회피다).

[안전] 조회 실패·캘린더 비어 있음 → 빈 집합(미개입 = 매수 정상 진행). 이 게이트가 매수를
통째로 막는 실패 모드는 없다. 캘린더가 비는 흔한 원인은 DART 무상증자 결정 공시를 아직
수집하지 못한 것이고, 그 경우 손실 위험은 종전과 같다(새로 생기는 위험은 없다).
"""
import logging
from datetime import date

from core.db import get_jongalab_db
from core.market_calendar import next_trading_day

logger = logging.getLogger("ExRights")


def fetch_ex_rights_on(on_date: date) -> dict[str, dict]:
    """그날 권리락인 종목 — {stk_cd: {ratio, record_date, corp_name}}."""
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT ticker, ratio, record_date, listing_date, corp_name "
            "FROM ex_rights_schedule WHERE ex_rights_date = %s",
            (on_date,),
        )
        return {r["ticker"]: r for r in cursor.fetchall()}


def get_next_session_ex_rights(today: date | None = None) -> dict[str, dict]:
    """**다음 거래일**(= 이 매수분의 청산일)이 권리락일인 종목. 실패 시 빈 dict(미개입).

    오늘이 권리락일인 종목은 대상이 아니다 — 조정이 이미 끝난 가격에 사서 다음날 파는 것은
    정상 거래다. 문제는 '권리부 가격에 사서 권리락 가격에 파는' 한 칸뿐이다.
    """
    base = today or date.today()
    try:
        target = next_trading_day(base)
        return fetch_ex_rights_on(target)
    except Exception as e:
        logger.warning("권리락 캘린더 조회 실패 — 미개입(매수 정상 진행): %s", e)
        return {}
