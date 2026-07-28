"""순위정보 (/api/dostk/rkinfo) — ka10032, ka90009, ka10037, ka10035, ka10098."""
from datetime import datetime


class RankMixin:
    # ────────────────────────────────────────────
    # 순위정보 (/api/dostk/rkinfo)
    # ────────────────────────────────────────────
    def get_trading_value_rank(self, mrkt_tp: str = "000", max_pages: int = 1) -> dict:
        """
        ka10032 — 거래대금상위요청
        mrkt_tp: 000=전체(양시장 통합), 001=코스피, 101=코스닥
        max_pages: 연속조회 페이지 수(1페이지=100행). 통합 조회는 ETF/ETN 과 양 시장이
                   한 리스트에 섞이므로 같은 거래대금 구간까지 내려가려면 시장별 조회보다
                   많은 행이 필요하다(2026-07-28 실측: 100행 끝이 780억).
        응답 shape 은 페이지 수와 무관하게 {"trde_prica_upper": [...]} 로 동일하다.
        """
        body = {
            "mrkt_tp": mrkt_tp,
            "mang_stk_incls": "0",  # 관리종목 미포함
            "stex_tp": "3",         # 1:KRX, 2:NXT 3.통합
        }
        if max_pages <= 1:
            return self._post(self.cfg.URL_RKINFO, "ka10032", body)

        items = self.fetch_all_pages(
            self.cfg.URL_RKINFO, "ka10032", body,
            "trde_prica_upper", max_pages=max_pages,
        )
        return {"trde_prica_upper": items, "return_code": 0}

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

    def get_after_hours_flu_rank(
        self, mrkt_tp: str = "000", sort_base: str = "1", stk_cnd: str = "16"
    ) -> dict:
        """
        ka10098 — 시간외단일가등락율순위요청
        16:00~18:00 시간외 단일가 등락률 순위 (시장 전체 스캔).
        mrkt_tp: 000=전체, 001=코스피, 101=코스닥
        sort_base: 1=상승률, 2=상승폭, 3=하락률, 4=하락폭, 5=보합
        stk_cnd: 0=전체, 16=ETF+ETN제외 (스펙상 단일 선택)
        응답: ovt_sigpric_flu_rt_rank (LIST) — flu_rt(시간외 등락률),
              tdy_close_pric_flu_rt(당일종가 등락률) 비교로 시간외 반응 측정
        """
        return self._post(self.cfg.URL_RKINFO, "ka10098", {
            "mrkt_tp": mrkt_tp,
            "sort_base": sort_base,
            "stk_cnd": stk_cnd,
            "trde_qty_cnd": "0",
            "crd_cnd": "0",
            "trde_prica": "0",
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
