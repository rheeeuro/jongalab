"""키움 REST 주문/계좌 클라이언트 (trading 전용).

이 도메인만 주문 권한을 가진다. kiwoom 데이터 서버(:8001)는 읽기 전용이므로
주문은 여기서 키움 REST(`/api/dostk/ordr`, `/api/dostk/acnt`)로 **직접** 호출한다.

토큰: kiwoom DB 의 공유 토큰을 읽기 전용으로 사용한다(발급/갱신은 kiwoom 워커 담당).
모드: TRADING_MODE='paper' 이면 실제 전송하지 않고 의도만 반환(시뮬레이션).

[사용 TR]
  kt10000  주식 매수주문   POST /api/dostk/ordr
  kt10001  주식 매도주문   POST /api/dostk/ordr
  kt00018  계좌평가잔고내역 POST /api/dostk/acnt
"""
import time
import logging

import requests

from core.config import (
    KIWOOM_USE_MOCK,
    TRADING_MODE,
    KIWOOM_ACCOUNT_NO,
)
from core.repository import kiwoom_token as token_repo

logger = logging.getLogger("TradingOrder")

_BASE_URL = "https://api.kiwoom.com"
_MOCK_URL = "https://mockapi.kiwoom.com"

_URL_ORDR = "/api/dostk/ordr"   # kt10000(매수), kt10001(매도)
_URL_ACNT = "/api/dostk/acnt"   # kt00018(잔고)

_TIMEOUT = 10


class TokenUnavailable(RuntimeError):
    """공유 토큰이 없거나 만료 — kiwoom 토큰 워커 점검 필요."""


class KiwoomOrderClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json;charset=UTF-8"})
        self._token: str | None = None

    @property
    def base_url(self) -> str:
        return _MOCK_URL if KIWOOM_USE_MOCK else _BASE_URL

    @property
    def paper(self) -> bool:
        return TRADING_MODE != "live"

    # ── 토큰: 공유 DB 에서 읽기만 ──
    def ensure_token(self) -> None:
        row = token_repo.get_token()
        if not row or not row.get("access_token"):
            raise TokenUnavailable("키움 공유 토큰 없음 — kiwoom-token-refresh 워커 확인 필요")
        # TODO: expires_dt 만료 판정 추가 (kiwoom.core.kiwoom_api._is_token_expired 참고)
        self._token = row["access_token"]

    def _headers(self, api_id: str) -> dict:
        return {
            "authorization": f"Bearer {self._token}",
            "api-id": api_id,
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _post(self, url_path: str, api_id: str, body: dict) -> dict:
        """주문/계좌 POST 공통. paper 모드면 전송하지 않고 시뮬레이션 응답."""
        if self.paper and api_id in ("kt10000", "kt10001"):
            logger.info("[PAPER] %s 미전송 (시뮬레이션): %s", api_id, body)
            return {"return_code": 0, "return_msg": "paper", "paper": True, "echo": body}

        self.ensure_token()
        url = f"{self.base_url}{url_path}"
        resp = self.session.post(url, headers=self._headers(api_id), json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("return_code", 0) != 0:
            logger.warning("[%s] %s", api_id, data.get("return_msg", "Unknown error"))
        time.sleep(0.15)
        return data

    # ── 주문 ──
    def buy(self, stk_cd: str, qty: int, price: int = 0, ord_type: str = "3") -> dict:
        """kt10000 — 매수주문. ord_type 기본 '3'(시장가). 지정가는 '0' + price."""
        return self._post(_URL_ORDR, "kt10000", {
            "dmst_stex_tp": "KRX",
            "stk_cd": stk_cd,
            "ord_qty": str(qty),
            "ord_uv": str(price),
            "trde_tp": ord_type,
        })

    def sell(self, stk_cd: str, qty: int, price: int = 0, ord_type: str = "3") -> dict:
        """kt10001 — 매도주문."""
        return self._post(_URL_ORDR, "kt10001", {
            "dmst_stex_tp": "KRX",
            "stk_cd": stk_cd,
            "ord_qty": str(qty),
            "ord_uv": str(price),
            "trde_tp": ord_type,
        })

    # ── 계좌 ──
    def get_balance(self) -> dict:
        """kt00018 — 계좌평가잔고내역요청 (reconcile 워커가 사용)."""
        return self._post(_URL_ACNT, "kt00018", {
            "qry_tp": "1",
            "dmst_stex_tp": "KRX",
            "acnt_no": KIWOOM_ACCOUNT_NO,
        })
