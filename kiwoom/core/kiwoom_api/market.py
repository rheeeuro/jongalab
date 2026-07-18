"""시세 (/api/dostk/mrktpr, /api/dostk/mrkcond) — ka10063(대체: ka10059), ka90008, ka90013, ka10087, ka10066, ka10046, ka10047."""
import time
from datetime import datetime


class MarketMixin:
    # ────────────────────────────────────────────
    # 시세 (/api/dostk/mrktpr)
    # ────────────────────────────────────────────
    def get_intraday_investor(self, stk_cd: str) -> dict:
        """ka10059 — 종목별투자자기관별요청 (ka10063 대체)"""
        return self.get_investor_by_stock(stk_cd)

    def get_program_trade_hourly(
        self, stk_cd: str, date: str = "", max_pages: int = 8, until_tm: str = "",
    ) -> dict:
        """
        ka90008 — 종목시간별프로그램매매추이요청
        당일 틱 단위 프로그램 매매 시계열 (최신→과거, 페이지당 200행 ≈ 25분).
        (구 구현 버그: URL_MRKTPR 로 보내 1504 오류로 사실상 미사용 — 실제 지원 URI 는
         URL_MRKCOND, 2026-07-19 수정. ka90013 처럼 통합 기준 → SOR 코드(_AL)로 조회.)
        until_tm("HHMMSS")을 주면 그 시각 이전 행에 도달한 페이지에서 조기 중단 —
        오전/오후 분해 피처가 12:00 경계까지만 필요할 때 페이지 낭비를 막는다.
        응답: stk_tm_prm_trde_trnsn (LIST) — tm(HHMMSS), prm_netprps_amt(당일 누적
              순매수, 백만원, 음수는 '--' 이중부호), prm_netprps_amt_irds(증감) 등
        """
        code = stk_cd if "_" in stk_cd else f"{stk_cd}_AL"
        body = {
            "amt_qty_tp": "1",      # 1:금액, 2:수량
            "stk_cd": code,
            "date": date or datetime.now().strftime("%Y%m%d"),
        }
        all_items: list = []
        cont_yn = ""
        next_key = ""
        for _ in range(max_pages):
            url = f"{self.base_url}{self.cfg.URL_MRKCOND}"
            headers = self._headers("ka90008", cont_yn, next_key)
            resp = self.session.post(url, headers=headers, json=body)
            resp.raise_for_status()
            items = resp.json().get("stk_tm_prm_trde_trnsn", [])
            all_items.extend(items)
            if until_tm and items and (items[-1].get("tm") or "999999") <= until_tm:
                break
            cont_yn = resp.headers.get("cont-yn", "N")
            next_key = resp.headers.get("next-key", "")
            if cont_yn != "Y" or not next_key:
                break
            time.sleep(0.3)
        return {"stk_tm_prm_trde_trnsn": all_items}

    def get_after_hours_single_price(self, stk_cd: str) -> dict:
        """
        ka10087 — 시간외단일가요청
        16:00~18:00 시간외 단일가 시세·호가 스냅샷 (익일 갭 선행지표).
        핵심 필드: ovt_sigpric_cur_prc(현재가), ovt_sigpric_flu_rt(등락률),
        ovt_sigpric_pred_pre(전일대비), ovt_sigpric_acc_trde_qty(누적거래량),
        ovt_sigpric_{sel,buy}_bid_tot_req(호가 총잔량)
        """
        return self._post(self.cfg.URL_MRKCOND, "ka10087", {
            "stk_cd": stk_cd,
        })

    def get_after_close_investor(
        self, mrkt_tp: str = "000", amt_qty_tp: str = "1",
        trde_tp: str = "0", stex_tp: str = "3", max_pages: int = 5,
    ) -> dict:
        """
        ka10066 — 장마감후투자자별매매요청
        장 마감 후 확정 투자자별 순매수 (시장 전체, 종목별 리스트).
        장중 잠정치(ka10059)와 달리 마감 후 확정치 — 수급 점수 사후 검증용.
        mrkt_tp: 000=전체, 001=코스피, 101=코스닥 / amt_qty_tp: 1=금액(백만원), 2=수량
        trde_tp: 0=순매수 / stex_tp: 3=통합
        응답: opaf_invsr_trde (LIST) — stk_cd, ind_invsr, frgnr_invsr, orgn,
              penfnd_etc(연기금) 등 투자자별 (연속조회 max_pages 까지 병합)
        """
        items = self.fetch_all_pages(
            self.cfg.URL_MRKCOND, "ka10066",
            {
                "mrkt_tp": mrkt_tp,
                "amt_qty_tp": amt_qty_tp,
                "trde_tp": trde_tp,
                "stex_tp": stex_tp,
            },
            list_key="opaf_invsr_trde", max_pages=max_pages,
        )
        return {"opaf_invsr_trde": items}

    def get_execution_strength_hourly(self, stk_cd: str) -> dict:
        """
        ka10046 — 체결강도추이시간별요청
        종목별 당일 시간별 체결강도 (15시 시점 진입 강도 팩터용).
        응답: cntr_str_tm (LIST) — cntr_tm(HHmmss), cntr_str(당시점),
              cntr_str_5min/20min/60min(분 단위 평균), stex_tp
        """
        return self._post(self.cfg.URL_MRKCOND, "ka10046", {
            "stk_cd": stk_cd,
        })

    def get_execution_strength_daily(self, stk_cd: str) -> dict:
        """
        ka10047 — 체결강도추이일별요청
        종목별 일별 체결강도(매수세/매도세 비율, 100 초과=매수 우위).
        응답: cntr_str_daly (LIST) — dt, cntr_str(당일), cntr_str_5min/20min/60min
              (필드명은 min 이지만 일별 TR 이므로 5/20/60일 평균)
        """
        return self._post(self.cfg.URL_MRKCOND, "ka10047", {
            "stk_cd": stk_cd,
        })

    def get_program_daily_trend(self, stk_cd: str) -> dict:
        """
        ka90013 — 종목일별프로그램매매추이요청
        종목별 일자 시계열 프로그램 매매 (수급 5일 추이용).
        프로그램 순매수는 통합(KRX+NXT) 기준으로 본다 → SOR 코드(_AL)로 조회.
        (stk_cd 가 이미 _NX/_AL 등 접미사를 가지면 그대로 사용)
        응답: stk_daly_prm_trde_trnsn (LIST) — dt, prm_netprps_amt(백만원) 등
        """
        code = stk_cd if "_" in stk_cd else f"{stk_cd}_AL"
        return self._post(self.cfg.URL_MRKCOND, "ka90013", {
            "amt_qty_tp": "",       # 빈값=금액, 1:금액, 2:수량
            "stk_cd": code,
            "date": "",             # 빈값=최신
        })
