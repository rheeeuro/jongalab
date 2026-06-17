"""테마 (/api/dostk/thme) — ka90001, ka90002."""


class ThemeMixin:
    # ────────────────────────────────────────────
    # 테마 (/api/dostk/thme)
    # ────────────────────────────────────────────
    def get_theme_groups(self, date_tp: str = "1", flu_pl_amt_tp: str = "3",
                        stex_tp: str = "3") -> dict:
        """
        ka90001 — 테마그룹별요청
        date_tp: n일전 기간수익률 (1~99)
        flu_pl_amt_tp: 1=상위기간수익률, 2=하위, 3=상위등락률, 4=하위등락률
        stex_tp: 1=KRX, 2=NXT, 3=통합
        응답: thema_grp (LIST) — thema_grp_cd, thema_nm, stk_num, flu_rt, dt_prft_rt, main_stk
        """
        return self._post(self.cfg.URL_THME, "ka90001", {
            "qry_tp": "0",
            "stk_cd": "",
            "date_tp": date_tp,
            "thema_nm": "",
            "flu_pl_amt_tp": flu_pl_amt_tp,
            "stex_tp": stex_tp,
        })

    def get_theme_stocks(self, thema_grp_cd: str, date_tp: str = "10",
                         stex_tp: str = "3") -> dict:
        """
        ka90002 — 테마구성종목요청
        thema_grp_cd: 테마그룹코드 (ka90001 응답의 thema_grp_cd)
        date_tp: n일전 (1~99)
        stex_tp: 1=KRX, 2=NXT, 3=통합
        응답: thema_comp_stk (LIST) — stk_cd, stk_nm, cur_prc, flu_rt 등
        """
        return self._post(self.cfg.URL_THME, "ka90002", {
            "date_tp": date_tp,
            "thema_grp_cd": thema_grp_cd,
            "stex_tp": stex_tp,
        })
