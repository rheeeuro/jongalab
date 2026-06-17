"""시세 (/api/dostk/mrktpr) — ka10063(대체: ka10059), ka90008."""
from datetime import datetime


class MarketMixin:
    # ────────────────────────────────────────────
    # 시세 (/api/dostk/mrktpr)
    # ────────────────────────────────────────────
    def get_intraday_investor(self, stk_cd: str) -> dict:
        """ka10059 — 종목별투자자기관별요청 (ka10063 대체)"""
        return self.get_investor_by_stock(stk_cd)

    def get_program_trade_hourly(self, stk_cd: str) -> dict:
        """
        ka90008 — 종목시간별프로그램매매추이요청
        시간대별 프로그램 매매 추이 (외국인 프로그램 확인)
        응답: stk_tm_prm_trde_trnsn (LIST)
        """
        return self._post(self.cfg.URL_MRKTPR, "ka90008", {
            "amt_qty_tp": "1",      # 1:금액, 2:수량
            "stk_cd": stk_cd,
            "date": datetime.now().strftime("%Y%m%d"),
        })
