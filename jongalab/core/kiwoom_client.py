"""키움 데이터 서버(HTTP) 클라이언트.

기존 core.kiwoom_api.KiwoomRestAPI 의 공개 메서드를 **동일한 이름·시그니처·반환
shape** 으로 미러링한다. 키움 연동이 별도 서버(localhost :8001)로 분리되면서,
소비자(market_data / sector_resolver / trading_engine / closing_bet / gap_check)는
이 클라이언트를 KiwoomRestAPI 자리에 그대로 주입받아 내부 로직 변경 없이 동작한다.

서버가 요청마다 토큰을 보장하므로 ensure_token() 은 no-op 이다.
"""
import logging

import requests

from core.config import KIWOOM_BASE_URL

logger = logging.getLogger("KiwoomClient")

# 키움 분봉 페이지네이션 등은 서버 측에서 수 초 걸릴 수 있어 넉넉히 잡는다.
_TIMEOUT = 30


class KiwoomRestClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or KIWOOM_BASE_URL).rstrip("/")

    def _post(self, path: str, body: dict):
        resp = requests.post(f"{self.base_url}{path}", json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ── 토큰: 서버가 요청마다 보장 → 클라이언트는 no-op ──
    def ensure_token(self) -> None:
        return None

    # ── 종목 정보 ──
    def get_stock_basic_info(self, stk_cd: str) -> dict:
        return self._post("/stock/basic-info", {"stk_cd": stk_cd})

    def get_stock_detail_info(self, stk_cd: str) -> dict:
        return self._post("/stock/detail-info", {"stk_cd": stk_cd})

    def get_stock_broker(self, stk_cd: str) -> dict:
        return self._post("/stock/broker", {"stk_cd": stk_cd})

    def get_stock_list(self, mrkt_tp: str = "0") -> dict:
        return self._post("/stock/list", {"mrkt_tp": mrkt_tp})

    def get_investor_by_stock(self, stk_cd: str) -> dict:
        return self._post("/stock/intraday-investor", {"stk_cd": stk_cd})

    # get_intraday_investor 는 원본에서 get_investor_by_stock 의 별칭
    def get_intraday_investor(self, stk_cd: str) -> dict:
        return self.get_investor_by_stock(stk_cd)

    def get_program_trade_by_stock(self, mrkt_tp: str = "P00101") -> dict:
        return self._post("/program-trade/by-stock", {"mrkt_tp": mrkt_tp})

    def get_program_daily_trend(self, stk_cd: str) -> dict:
        return self._post("/program-trade/daily-trend", {"stk_cd": stk_cd})

    def get_inst_foreign_consecutive(self, mrkt_tp: str = "001") -> dict:
        return self._post("/inst-foreign/consecutive", {"mrkt_tp": mrkt_tp})

    # ── 차트 ──
    def get_daily_chart(self, stk_cd: str, dt: str = "", upd_stk_prc: str = "1") -> dict:
        return self._post(
            "/chart/daily", {"stk_cd": stk_cd, "dt": dt, "upd_stk_prc": upd_stk_prc}
        )

    def get_minute_chart_pages(
        self, stk_cd: str, tic_scope: str = "60", base_dt: str = "", max_pages: int = 5
    ) -> list:
        return self._post(
            "/chart/minute-pages",
            {
                "stk_cd": stk_cd,
                "tic_scope": tic_scope,
                "base_dt": base_dt,
                "max_pages": max_pages,
            },
        )

    # ── 순위 ──
    def get_trading_value_rank(self, mrkt_tp: str = "001") -> dict:
        return self._post("/rank/trading-value", {"mrkt_tp": mrkt_tp})

    # ── 테마 ──
    def get_theme_groups(
        self, date_tp: str = "1", flu_pl_amt_tp: str = "3", stex_tp: str = "3"
    ) -> dict:
        return self._post(
            "/theme/groups",
            {"date_tp": date_tp, "flu_pl_amt_tp": flu_pl_amt_tp, "stex_tp": stex_tp},
        )

    def get_theme_stocks(
        self, thema_grp_cd: str, date_tp: str = "10", stex_tp: str = "3"
    ) -> dict:
        return self._post(
            "/theme/stocks",
            {"thema_grp_cd": thema_grp_cd, "date_tp": date_tp, "stex_tp": stex_tp},
        )
