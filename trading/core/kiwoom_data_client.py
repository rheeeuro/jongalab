"""키움 데이터 서버(:8001) HTTP 클라이언트 — 시세 조회 (읽기 전용).

trading 은 주문/계좌는 키움 REST 로 직접(kiwoom_order_client), 시세는 kiwoom
데이터 서버를 통해 읽는다. 사이징(현재가)·청산·정합성에서 사용한다.
"""
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests

from core.config import KIWOOM_BASE_URL

logger = logging.getLogger("TradingData")

_TIMEOUT = 10

_KST = ZoneInfo("Asia/Seoul")
_KRX_OPEN = time(9, 0)    # 정규장 개장
_KRX_CLOSE = time(15, 30)  # 정규장 마감


def _in_krx_session(now: datetime | None = None) -> bool:
    """현재가 KRX 정규장 시간(평일 09:00–15:30)인지."""
    now = now or datetime.now(_KST)
    if now.weekday() >= 5:  # 토/일
        return False
    return _KRX_OPEN <= now.time() <= _KRX_CLOSE


def to_int(v) -> int:
    """키움 숫자 문자열(0-패딩·+/- 부호 가능)을 int 로. 빈값/오류는 0."""
    if v is None:
        return 0
    s = str(v).strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


class KiwoomDataClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or KIWOOM_BASE_URL).rstrip("/")

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(f"{self.base_url}{path}", json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def get_stock_basic_info(self, stk_cd: str) -> dict:
        """ka10001 — 주식기본정보 (cur_prc 등)."""
        return self._post("/stock/basic-info", {"stk_cd": stk_cd})

    def get_stock_detail_info(self, stk_cd: str) -> dict:
        """ka10100 — 종목정보조회 (nxtEnable, marketName 등)."""
        return self._post("/stock/detail-info", {"stk_cd": stk_cd})

    def get_daily_chart(self, stk_cd: str, dt: str = "", upd_stk_prc: str = "1") -> dict:
        """ka10081 — 주식일봉차트 (최신순 캔들 리스트)."""
        return self._post(
            "/chart/daily", {"stk_cd": stk_cd, "dt": dt, "upd_stk_prc": upd_stk_prc}
        )

    def get_minute_chart_pages(self, stk_cd: str, tic_scope: str = "1",
                               base_dt: str = "", max_pages: int = 2) -> list:
        """ka10080 — 분봉 차트 연속조회. base_dt(YYYYMMDD) 기준 최신→과거 순 bar 리스트.
        1페이지 ≈ 900봉(≈2.3거래일)이라 max_pages=2 면 매수날~매도날 구간을 넉넉히 덮는다.
        bar 필드: cntr_tm(YYYYMMDDHHMMSS)·open_pric·high_pric·low_pric·cur_prc(종가)·trde_qty."""
        resp = requests.post(
            f"{self.base_url}/chart/minute-pages",
            json={"stk_cd": stk_cd, "tic_scope": tic_scope, "base_dt": base_dt, "max_pages": max_pages},
            timeout=30,  # 연속조회(페이지당 0.3s sleep)라 기본 10s 보다 길게
        )
        resp.raise_for_status()
        return resp.json()

    def is_nxt_enabled(self, stk_cd: str) -> bool:
        """NXT(넥스트레이드) 거래 가능 종목인지. 조회 실패 시 False(보수적)."""
        try:
            d = self.get_stock_detail_info(stk_cd)
        except Exception as e:
            logger.warning("NXT 여부 조회 실패 [%s]: %s", stk_cd, e)
            return False
        return str(d.get("nxtEnable", "")).upper() == "Y"

    def get_current_price(self, stk_cd: str) -> int:
        """현재가(원, 양수). 조회 실패 시 0."""
        try:
            info = self.get_stock_basic_info(stk_cd)
        except Exception as e:
            logger.warning("현재가 조회 실패 [%s]: %s", stk_cd, e)
            return 0
        return abs(to_int(info.get("cur_prc")))

    def get_nxt_last_close(self, stk_cd: str) -> int:
        """NXT 보드의 가장 최근 체결 종가(원, 양수).

        장외 시간엔 ka10001 `cur_prc`(_NX)가 NXT 종가가 아니라 기준가(=KRX
        종가)를 돌려주므로, NXT 일봉(_NX)에서 거래량>0 인 최신 캔들의 종가
        (`cur_prc`)를 쓴다. NXT 거래시간 중엔 당일 캔들이 실시간 갱신돼 현재
        NXT 시세가 된다. 조회 실패/데이터 없음 시 0.
        """
        try:
            data = self.get_daily_chart(f"{stk_cd}_NX")
        except Exception as e:
            logger.warning("NXT 일봉 조회 실패 [%s]: %s", stk_cd, e)
            return 0
        for c in data.get("stk_dt_pole_chart_qry", []):
            if to_int(c.get("trde_qty")) > 0:
                return abs(to_int(c.get("cur_prc")))
        return 0

    def get_display_price(self, stk_cd: str) -> tuple[int, bool]:
        """대시보드 표시용 현재가.
        정규장(평일 09:00–15:30) 중에는 정규장(KRX) 가격을 그대로 보여주고,
        정규장 외 시간에는 NXT 가능 종목에 한해 NXT 종가(가장 최근 NXT 체결가)를
        우선 보여준다(NXT 시세가 없으면 KRX 로 폴백).
        반환: (price, is_nxt) — is_nxt 는 반환 price 가 NXT 보드 시세인지 여부.
        """
        if not _in_krx_session() and self.is_nxt_enabled(stk_cd):
            nxt = self.get_nxt_last_close(stk_cd)
            if nxt:
                return nxt, True
        return self.get_current_price(stk_cd), False

    def get_market_price(self, stk_cd: str) -> int:
        """체결·청산 판정용 현재가(원, 양수). 조회 실패 시 0.

        정규장 외(NXT 시간대)에는 ka10001 `cur_prc` 가 NXT 시세가 아니라 기준가
        (=전일 KRX 종가)를 돌려주므로, 그대로 쓰면 settle/monitor 가 NXT 실시간가를
        못 보고 죽은 기준가로 손절·스탑·트레일링을 판정한다. get_display_price 와
        동일한 NXT-aware 판정(정규장 외 + NXT 가능 → NXT 최근 체결가, 그 외 KRX)을
        써서 실제 거래 가능한 시세를 돌려준다."""
        return self.get_display_price(stk_cd)[0]
