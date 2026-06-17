"""키움 데이터 서버(:8001) HTTP 클라이언트 — 시세 조회 (읽기 전용).

trading 은 주문/계좌는 키움 REST 로 직접(kiwoom_order_client), 시세는 kiwoom
데이터 서버를 통해 읽는다. 사이징(현재가)·청산·정합성에서 사용한다.
"""
import logging

import requests

from core.config import KIWOOM_BASE_URL

logger = logging.getLogger("TradingData")

_TIMEOUT = 10


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
