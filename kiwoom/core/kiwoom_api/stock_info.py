"""종목정보 (/api/dostk/stkinfo) — ka10001, ka10100, ka10002, ka10059, ka90004."""
from datetime import datetime


class StockInfoMixin:
    # ────────────────────────────────────────────
    # 종목정보 (/api/dostk/stkinfo)
    # ────────────────────────────────────────────
    def get_stock_basic_info(self, stk_cd: str) -> dict:
        """
        ka10001 — 주식기본정보요청
        응답: stk_cd, stk_nm, cur_prc, pred_pre, pre_sig, mac(시가총액),
              trde_qty, flo_stk, oyr_hgst, oyr_lwst, 250hgst, 250lwst 등
        """
        return self._post(self.cfg.URL_STKINFO, "ka10001", {
            "stk_cd": stk_cd,
        })

    def get_stock_detail_info(self, stk_cd: str) -> dict:
        """
        ka10100 — 종목정보조회
        응답: code, name, upName(업종명), upSizeName(회사크기분류),
              marketName(시장명), companyClassName, listCount 등
        """
        return self._post(self.cfg.URL_STKINFO, "ka10100", {
            "stk_cd": stk_cd,
        })

    def get_stock_broker(self, stk_cd: str) -> dict:
        """
        ka10002 — 주식거래원요청
        응답: 매도상위5/매수상위5 거래원 정보
        """
        return self._post(self.cfg.URL_STKINFO, "ka10002", {
            "stk_cd": stk_cd,
        })

    def get_investor_by_stock(self, stk_cd: str) -> dict:
        """
        ka10059 — 종목별투자자기관별요청
        응답: 개인/외국인/기관 순매수 수량·금액
        """
        return self._post(self.cfg.URL_STKINFO, "ka10059", {
            "stk_cd": stk_cd,
            "dt": datetime.now().strftime("%Y%m%d"),
            "amt_qty_tp": "1",  # 1:금액, 2:수량
            "trde_tp": "0",     # 0:순매수, 1:매수, 2:매도
            "unit_tp": "1000",  # 1000:천주, 1:단주
        })

    def get_stock_list(self, mrkt_tp: str = "0") -> dict:
        """
        ka10099 — 종목정보 리스트 (시장별 상장종목 전체)
        mrkt_tp: "0"=코스피, "10"=코스닥
        응답: list (LIST) — code, name, marketName, upName(업종), auditInfo 등
        """
        return self._post(self.cfg.URL_STKINFO, "ka10099", {
            "mrkt_tp": mrkt_tp,
        })

    def get_program_trade_by_stock(self, mrkt_tp: str = "P00101") -> dict:
        """
        ka90004 — 종목별프로그램매매현황요청
        시장 전체 종목별 프로그램 매매 현황 조회
        응답: stk_prm_trde_prst (LIST) — stk_cd, netprps_prica 등
        """
        return self._post(self.cfg.URL_STKINFO, "ka90004", {
            "dt": datetime.now().strftime("%Y%m%d"),
            "mrkt_tp": mrkt_tp,
            "stex_tp": "3",
        })
