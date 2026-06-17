"""차트 (/api/dostk/chart) — ka10080(분봉), ka10081(일봉)."""
from datetime import datetime


class ChartMixin:
    # ────────────────────────────────────────────
    # 차트 (/api/dostk/chart)
    # ────────────────────────────────────────────
    def get_minute_chart(self, stk_cd: str, tic_scope: str = "60",
                         base_dt: str = "") -> dict:
        """
        ka10080 — 주식분봉차트조회요청
        tic_scope: 1, 3, 5, 10, 15, 30, 45, 60 (분)
        base_dt: 기준일자 (YYYYMMDD, 빈값=오늘)
        응답: stk_min_pole_chart_qry (LIST) — cur_prc, trde_qty,
              cntr_tm, open_pric, high_pric, low_pric 등
        """
        if not base_dt:
            base_dt = datetime.now().strftime("%Y%m%d")
        body = {
            "stk_cd": stk_cd,
            "tic_scope": tic_scope,
            "upd_stkpc_tp": "1",
            "base_dt": base_dt,
        }
        return self._post(self.cfg.URL_CHART, "ka10080", body)

    def get_minute_chart_pages(self, stk_cd: str, tic_scope: str = "60",
                               base_dt: str = "", max_pages: int = 5) -> list:
        """ka10080 연속조회로 분봉 데이터 다건 수집"""
        if not base_dt:
            base_dt = datetime.now().strftime("%Y%m%d")
        body = {
            "stk_cd": stk_cd,
            "tic_scope": tic_scope,
            "upd_stkpc_tp": "1",
            "base_dt": base_dt,
        }
        return self.fetch_all_pages(
            self.cfg.URL_CHART, "ka10080", body,
            list_key="stk_min_pole_chart_qry",
            max_pages=max_pages,
        )

    def get_daily_chart(self, stk_cd: str, dt: str = "",
                        upd_stk_prc: str = "1") -> dict:
        """
        ka10081 — 주식일봉차트조회요청
        dt: 기준일자 (YYYYMMDD, 빈값=오늘)
        upd_stk_prc: 수정주가 사용 여부 (1:사용)
        응답: stk_dt_pole (LIST) — dt, open_prc, high_prc, low_prc,
              cur_prc, trde_qty 등
        """
        if not dt:
            dt = datetime.now().strftime("%Y%m%d")
        body = {"stk_cd": stk_cd, "base_dt": dt, "upd_stkpc_tp": upd_stk_prc}
        return self._post(self.cfg.URL_CHART, "ka10081", body)
