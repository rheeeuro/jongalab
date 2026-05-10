"""
키움증권 REST API 클라이언트
============================================================
도메인: api.kiwoom.com (운영) / mockapi.kiwoom.com (모의투자)
인증:   au10001 (OAuth2 토큰 발급)
헤더:   authorization, api-id, cont-yn, next-key

[사용 TR 목록]
  au10001  접근토큰 발급          POST /oauth2/token
  au10002  접근토큰 폐기          POST /oauth2/token
  ka10001  주식기본정보요청        POST /api/dostk/stkinfo
  ka10100  종목정보조회            POST /api/dostk/stkinfo
  ka10002  주식거래원요청          POST /api/dostk/stkinfo
  ka10032  거래대금상위요청        POST /api/dostk/rkinfo
  ka10059  종목별투자자기관별요청  POST /api/dostk/stkinfo
  ka10063  장중투자자별매매요청    POST /api/dostk/mrktpr
  ka10080  주식분봉차트조회요청    POST /api/dostk/chart
  ka10081  주식일봉차트조회요청    POST /api/dostk/chart
  ka10131  기관외국인연속매매현황  POST /api/dostk/frgnistt
  ka90001  테마그룹별요청          POST /api/dostk/thme
  ka90002  테마구성종목요청        POST /api/dostk/thme
  ka90004  종목별프로그램매매현황  POST /api/dostk/stkinfo
  ka90008  종목시간별프로그램매매  POST /api/dostk/mrktpr
  ka90009  외국인기관매매상위요청  POST /api/dostk/rkinfo
  kt00001  예수금상세현황요청      POST /api/dostk/acnt
  kt00018  계좌평가잔고내역요청    POST /api/dostk/acnt
  kt10000  주식 매수주문           POST /api/dostk/ordr
  kt10001  주식 매도주문           POST /api/dostk/ordr
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

from core.repository import kiwoom_token as token_repo

load_dotenv()

logger = logging.getLogger("ClosingBet")


# ============================================================
# 설정 & 상수
# ============================================================

class KiwoomConfig:
    # ---- 키움 REST API ----
    BASE_URL = "https://api.kiwoom.com"           # 운영 도메인
    MOCK_URL = "https://mockapi.kiwoom.com"        # 모의투자 (KRX만 지원)
    USE_MOCK = False                                # True면 모의투자 사용

    APP_KEY = os.getenv("KIWOOM_APP_KEY", "")
    SECRET_KEY = os.getenv("KIWOOM_SECRET_KEY", "")
    ACCESS_TOKEN = ""

    # ---- URL 패턴 (키움 REST API 공식 엔드포인트) ----
    URL_TOKEN  = "/oauth2/token"        # 토큰 발급
    URL_STKINFO = "/api/dostk/stkinfo"  # 종목정보 (ka10001, ka10002, ka90004 등)
    URL_MRKTPR  = "/api/dostk/mrktpr"   # 시세 (ka10005, ka10063, ka90008 등)
    URL_RKINFO  = "/api/dostk/rkinfo"   # 순위정보 (ka10032, ka90009 등)
    URL_THME    = "/api/dostk/thme"    # 테마 (ka90001, ka90002)
    URL_FRINST  = "/api/dostk/frgnistt"  # 기관/외국인 (ka10008, ka10009, ka10131)
    URL_CHART   = "/api/dostk/chart"    # 차트 (ka10081 등)
    URL_ORDR    = "/api/dostk/ordr"     # 주문 (kt10000, kt10001 등)
    URL_ACNT    = "/api/dostk/acnt"     # 계좌 (kt00001, kt00018 등)

    EXCHANGE = "KRX"                          # KRX, NXT, SOR


# ============================================================
# 토큰 만료 판정 (5분 마진)
# ============================================================
_EXPIRY_MARGIN = timedelta(minutes=5)


def _is_token_expired(expires_dt: str | None) -> bool:
    """expires_dt(YYYYMMDDHHMMSS)가 현재시각 + 5분 이내이면 만료."""
    if not expires_dt:
        return True
    try:
        exp = datetime.strptime(expires_dt, "%Y%m%d%H%M%S")
    except ValueError:
        return True
    return datetime.now() + _EXPIRY_MARGIN >= exp


# ============================================================
# 키움 REST API 클라이언트
# ============================================================

class KiwoomRestAPI:
    """
    키움증권 REST API 래퍼 — 공식 명세 기반
    모든 TR은 POST 방식, JSON Body로 요청
    """

    def __init__(self, config: KiwoomConfig):
        self.cfg = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json;charset=UTF-8"
        })

    @property
    def base_url(self) -> str:
        return self.cfg.MOCK_URL if self.cfg.USE_MOCK else self.cfg.BASE_URL

    # ────────────────────────────────────────────
    # 인증
    # ────────────────────────────────────────────
    def get_access_token(self):
        """au10001 — 접근토큰 발급 + DB 저장"""
        url = f"{self.base_url}{self.cfg.URL_TOKEN}"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.cfg.APP_KEY,
            "secretkey": self.cfg.SECRET_KEY,
        }
        resp = self.session.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        self.cfg.ACCESS_TOKEN = data["token"]
        expires_dt = data.get("expires_dt")
        try:
            token_repo.save_token(self.cfg.ACCESS_TOKEN, expires_dt)
        except Exception as e:
            logger.warning(f"토큰 DB 저장 실패: {e}")
        logger.info(f"토큰 발급 완료 (만료: {expires_dt or 'N/A'})")

    def revoke_access_token(self):
        """au10002 — 접근토큰 폐기"""
        url = f"{self.base_url}{self.cfg.URL_TOKEN}"
        body = {
            "appkey": self.cfg.APP_KEY,
            "secretkey": self.cfg.SECRET_KEY,
            "token": self.cfg.ACCESS_TOKEN,
        }
        try:
            resp = self.session.post(url, json=body, headers={"api-id": "au10002"})
            resp.raise_for_status()
            self.cfg.ACCESS_TOKEN = ""
            try:
                token_repo.clear_token()
            except Exception as e:
                logger.warning(f"토큰 DB 정리 실패: {e}")
            logger.info("토큰 폐기 완료")
        except Exception as e:
            logger.warning(f"토큰 폐기 실패: {e}")

    def ensure_token(self):
        """DB에서 유효 토큰을 로드. 없거나 만료 임박이면 새로 발급."""
        try:
            row = token_repo.get_token()
        except Exception as e:
            logger.warning(f"토큰 DB 조회 실패: {e}")
            row = None

        if row and row.get("access_token") and not _is_token_expired(row.get("expires_dt")):
            self.cfg.ACCESS_TOKEN = row["access_token"]
            logger.info(f"DB 토큰 사용 (만료: {row.get('expires_dt') or 'N/A'})")
            return

        self.get_access_token()

    # ────────────────────────────────────────────
    # 공통 요청 메서드
    # ────────────────────────────────────────────
    def _headers(self, api_id: str, cont_yn: str = "", next_key: str = "") -> dict:
        """키움 REST API 공통 헤더"""
        h = {
            "authorization": f"Bearer {self.cfg.ACCESS_TOKEN}",
            "api-id": api_id,
            "Content-Type": "application/json;charset=UTF-8",
        }
        if cont_yn:
            h["cont-yn"] = cont_yn
        if next_key:
            h["next-key"] = next_key
        return h

    def _post(self, url_path: str, api_id: str, body: dict,
              cont_yn: str = "", next_key: str = "",
              max_retries: int = 3) -> dict:
        """POST 요청 공통 (429 rate limit 자동 재시도)"""
        url = f"{self.base_url}{url_path}"
        headers = self._headers(api_id, cont_yn, next_key)
        for attempt in range(max_retries):
            resp = self.session.post(url, headers=headers, json=body)
            if resp.status_code == 429:
                wait = 1.0 * (attempt + 1)
                logger.warning(f"[{api_id}] 429 rate limit — {wait:.0f}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("return_code", 0) != 0:
                logger.warning(f"[{api_id}] {data.get('return_msg', 'Unknown error')}")
            time.sleep(0.15)
            return data
        resp.raise_for_status()
        return {}

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

    # ────────────────────────────────────────────
    # 기관/외국인 (/api/dostk/frinst)
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

    # ────────────────────────────────────────────
    # 주문 (/api/dostk/ordr)
    # ────────────────────────────────────────────
    def place_buy_order(self, stk_cd: str, qty: int, price: int,
                        trde_tp: str = "0") -> dict:
        """
        kt10000 — 주식 매수주문
        trde_tp: 0=보통(지정가), 3=시장가, 5=조건부지정가,
                 6=최유리, 7=최우선, 81=장마감후시간외
        """
        body = {
            "dmst_stex_tp": self.cfg.EXCHANGE,
            "stk_cd": stk_cd,
            "ord_qty": str(qty),
            "trde_tp": trde_tp,
        }
        if trde_tp == "0":  # 지정가일 때만 단가 필요
            body["ord_uv"] = str(price)
        return self._post(self.cfg.URL_ORDR, "kt10000", body)

    def place_sell_order(self, stk_cd: str, qty: int, price: int,
                         trde_tp: str = "0") -> dict:
        """
        kt10001 — 주식 매도주문
        """
        body = {
            "dmst_stex_tp": self.cfg.EXCHANGE,
            "stk_cd": stk_cd,
            "ord_qty": str(qty),
            "trde_tp": trde_tp,
        }
        if trde_tp == "0":
            body["ord_uv"] = str(price)
        return self._post(self.cfg.URL_ORDR, "kt10001", body)

    # ────────────────────────────────────────────
    # 계좌 (/api/dostk/acnt)
    # ────────────────────────────────────────────
    def get_deposit(self) -> dict:
        """kt00001 — 예수금상세현황요청"""
        return self._post(self.cfg.URL_ACNT, "kt00001", {
            "qry_tp": "3",  # 3:추정조회, 2:일반조회
        })

    def get_evaluation_balance(self) -> dict:
        """
        kt00018 — 계좌평가잔고내역요청
        응답: tot_evlt_amt, tot_pur_amt, tot_evlt_pl, acnt_evlt_remn_indv_tot (LIST) 등
        """
        return self._post(self.cfg.URL_ACNT, "kt00018", {
            "qry_tp": "1",              # 1:합산, 2:개별
            "dmst_stex_tp": "KRX",      # KRX:한국거래소, NXT:넥스트트레이드
        })

    # ────────────────────────────────────────────
    # 유틸: 연속조회 처리
    # ────────────────────────────────────────────
    def fetch_all_pages(self, url_path: str, api_id: str, body: dict,
                        list_key: str, max_pages: int = 5) -> list:
        """연속조회(cont-yn/next-key) 자동 처리"""
        all_items = []
        cont_yn = ""
        next_key = ""

        for _ in range(max_pages):
            url = f"{self.base_url}{url_path}"
            headers = self._headers(api_id, cont_yn, next_key)
            resp = self.session.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

            items = data.get(list_key, [])
            all_items.extend(items)

            # 응답 헤더에서 연속조회 정보 확인
            resp_cont = resp.headers.get("cont-yn", "N")
            resp_next = resp.headers.get("next-key", "")

            if resp_cont != "Y" or not resp_next:
                break

            cont_yn = resp_cont
            next_key = resp_next
            time.sleep(0.3)

        return all_items
