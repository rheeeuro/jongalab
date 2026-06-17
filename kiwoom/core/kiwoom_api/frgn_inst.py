"""기관/외국인 (/api/dostk/frgnistt) — ka10131, ka10008, ka10009."""


class FrgnInstMixin:
    # ────────────────────────────────────────────
    # 기관/외국인 (/api/dostk/frgnistt)
    # ────────────────────────────────────────────
    def get_inst_foreign_consecutive(self, mrkt_tp: str = "001") -> dict:
        """
        ka10131 — 기관외국인연속매매현황요청
        시장 전체 기관/외국인 연속 순매수 랭킹 조회
        응답: orgn_frgnr_cont_trde_prst (LIST)
        """
        return self._post(self.cfg.URL_FRINST, "ka10131", {
            "dt": "5",
            "strt_dt": "",
            "end_dt": "",
            "mrkt_tp": mrkt_tp,
            "netslmt_tp": "2",       # 순매수 고정
            "stk_inds_tp": "0",      # 종목(주식)
            "amt_qty_tp": "0",       # 금액
            "stex_tp": "3",          # 통합
        })

    def get_foreign_trend(self, stk_cd: str) -> dict:
        """
        ka10008 — 주식외국인종목별매매동향
        """
        return self._post(self.cfg.URL_FRINST, "ka10008", {
            "stk_cd": stk_cd,
        })

    def get_institution_trend(self, stk_cd: str) -> dict:
        """
        ka10009 — 주식기관요청
        """
        return self._post(self.cfg.URL_FRINST, "ka10009", {
            "stk_cd": stk_cd,
        })
