"""공매도·대차거래 (/api/dostk/shsa, /api/dostk/slb) — ka10014, ka20068."""
from datetime import datetime, timedelta


class ShortSaleMixin:
    # ────────────────────────────────────────────
    # 공매도 (/api/dostk/shsa)
    # ────────────────────────────────────────────
    def get_short_sale_trend(self, stk_cd: str, strt_dt: str = "", end_dt: str = "") -> dict:
        """
        ka10014 — 공매도추이요청
        종목별 일별 공매도량/비중 시계열 (악재 veto 연구용).
        strt_dt/end_dt: YYYYMMDD (빈값이면 최근 30일)
        응답: shrts_trnsn (LIST) — dt, shrts_qty(공매도량), trde_wght(매매비중%),
              shrts_trde_prica(공매도거래대금 천원), shrts_avg_pric(공매도평균가)
        """
        end = end_dt or datetime.now().strftime("%Y%m%d")
        strt = strt_dt or (
            datetime.strptime(end, "%Y%m%d") - timedelta(days=30)
        ).strftime("%Y%m%d")
        return self._post(self.cfg.URL_SHSA, "ka10014", {
            "stk_cd": stk_cd,
            "tm_tp": "1",       # 0:시작일, 1:기간
            "strt_dt": strt,
            "end_dt": end,
        })

    def get_stock_lending_trend(self, stk_cd: str, strt_dt: str = "", end_dt: str = "") -> dict:
        """
        ka20068 — 대차거래추이요청(종목별)
        대차잔고 증감 시계열 (공매도 대기 물량 — 하방 압력 선행지표).
        strt_dt/end_dt: YYYYMMDD (빈값이면 최근 30일)
        응답: dbrt_trde_trnsn (LIST) — dt, dbrt_trde_cntrcnt(체결주수),
              dbrt_trde_rpy(상환주수), dbrt_trde_irds(증감), rmnd(잔고주수),
              remn_amt(잔고금액 백만원)
        """
        end = end_dt or datetime.now().strftime("%Y%m%d")
        strt = strt_dt or (
            datetime.strptime(end, "%Y%m%d") - timedelta(days=30)
        ).strftime("%Y%m%d")
        return self._post(self.cfg.URL_SLB, "ka20068", {
            "strt_dt": strt,
            "end_dt": end,
            "all_tp": "0",      # 0:입력 종목만
            "stk_cd": stk_cd,
        })
