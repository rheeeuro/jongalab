"""
키움 REST 클라이언트 — 기반 모듈 (설정·인증·공통 요청·연속조회).

KiwoomConfig 와 _BaseClient(토큰 발급/보장, _headers/_post, fetch_all_pages)를 정의한다.
카테고리별 Mixin(stock_info/market/rank/theme/frgn_inst/chart)이 self._post 를 호출하고,
__init__.py 가 이들을 _BaseClient 와 합쳐 KiwoomRestAPI 로 조립한다.

데이터 조회 전용 — 주문(/api/dostk/ordr)·계좌(/api/dostk/acnt)는 여기서 다루지 않는다
(주문/계좌 권한은 trading 도메인이 가진다).
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

    # ---- URL 패턴 (데이터 조회 전용 엔드포인트) ----
    URL_TOKEN  = "/oauth2/token"        # 토큰 발급
    URL_STKINFO = "/api/dostk/stkinfo"  # 종목정보 (ka10001, ka10002, ka90004 등)
    URL_MRKTPR  = "/api/dostk/mrktpr"   # 시세 (ka10005, ka10063, ka90008 등)
    URL_RKINFO  = "/api/dostk/rkinfo"   # 순위정보 (ka10032, ka90009 등)
    URL_THME    = "/api/dostk/thme"    # 테마 (ka90001, ka90002)
    URL_FRINST  = "/api/dostk/frgnistt"  # 기관/외국인 (ka10008, ka10009, ka10131)
    URL_CHART   = "/api/dostk/chart"    # 차트 (ka10081 등)


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
# 기반 클라이언트 — 설정·인증·공통 요청·연속조회
# ============================================================

class _BaseClient:
    """
    키움 REST 공통 인프라. 카테고리 Mixin 들이 이 클래스를 베이스로 조립된다.
    모든 TR은 POST 방식, JSON Body로 요청.
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
