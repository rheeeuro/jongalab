"""순위정보 (/api/dostk/rkinfo) — ka10032, ka90009, ka10037, ka10035."""
from datetime import datetime


class RankMixin:
    # ────────────────────────────────────────────
    # 순위정보 (/api/dostk/rkinfo)
    # ────────────────────────────────────────────
    def get_trading_value_rank(self, mrkt_tp: str = "001") -> dict:
        """
        ka10032 — 거래대금상위요청
        mrkt_tp: 001=코스피, 101=코스닥
        """
        return self._post(self.cfg.URL_RKINFO, "ka10032", {
            "mrkt_tp": mrkt_tp,
            "mang_stk_incls": "0",  # 관리종목 미포함
            "stex_tp": "3",         # 1:KRX, 2:NXT 3.통합
        })

    def get_foreign_inst_top(self, mrkt_tp: str = "001") -> dict:
        """
        ka90009 — 외국인기관매매상위요청
        응답: frgnr_orgn_trde_upper (LIST)
        """
        return self._post(self.cfg.URL_RKINFO, "ka90009", {
            "mrkt_tp": mrkt_tp,
            "amt_qty_tp": "1",      # 1:금액(천만), 2:수량(천)
            "qry_dt_tp": "1",       # 1:조회일자 포함
            "date": datetime.now().strftime("%Y%m%d"),
            "stex_tp": "3",         # 통합
        })

    def get_foreign_broker_top(self, mrkt_tp: str = "001") -> dict:
        """
        ka10037 — 외국계창구매매상위요청
        외국계 증권사 창구 순매수 상위
        """
        return self._post(self.cfg.URL_RKINFO, "ka10037", {
            "mrkt_tp": mrkt_tp,
            "sort_tp": "1",
            "trde_qty_tp": "0000",
            "stk_cnd": "1",
            "crd_cnd": "0",
            "stex_tp": "3",
        })

    def get_foreign_consecutive_buy(self, mrkt_tp: str = "001") -> dict:
        """
        ka10035 — 외인연속순매매상위요청
        """
        return self._post(self.cfg.URL_RKINFO, "ka10035", {
            "mrkt_tp": mrkt_tp,
            "sort_tp": "1",
            "trde_qty_tp": "0000",
            "stk_cnd": "1",
            "crd_cnd": "0",
            "stex_tp": "3",
        })
