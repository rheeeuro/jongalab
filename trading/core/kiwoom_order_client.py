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
)
from core.repository import kiwoom_token as token_repo

logger = logging.getLogger("TradingOrder")

_BASE_URL = "https://api.kiwoom.com"
_MOCK_URL = "https://mockapi.kiwoom.com"

_URL_ORDR = "/api/dostk/ordr"   # kt10000(매수), kt10001(매도), kt10002(정정), kt10003(취소)
_URL_ACNT = "/api/dostk/acnt"   # kt00018(잔고), kt00001(예수금) 등

# 주문 변경 TR — paper 모드에서 실제 전송하지 않고 시뮬레이션한다.
_ORDER_TRS = {"kt10000", "kt10001", "kt10002", "kt10003"}

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
        if self.paper and api_id in _ORDER_TRS:
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
    # trde_tp(매매구분): 0:보통(지정가), 3:시장가, 5:조건부지정가, 6:최유리, 7:최우선,
    #   10:보통(IOC), 20:보통(FOK) 등. 시장가는 ord_uv 를 빈 문자열로 보낸다.
    @staticmethod
    def _order_body(stk_cd: str, qty: int, price: int, trde_tp: str) -> dict:
        return {
            "dmst_stex_tp": "KRX",                       # KRX, NXT, SOR
            "stk_cd": stk_cd,
            "ord_qty": str(qty),                         # 단위: 1주
            "ord_uv": str(price) if price and price > 0 else "",  # 시장가면 "" (단위: 원)
            "trde_tp": trde_tp,
            "cond_uv": "",                               # 조건단가 (조건부지정가 등에서만 사용)
        }

    def buy(self, stk_cd: str, qty: int, price: int = 0, trde_tp: str = "3") -> dict:
        """kt10000 — 매수주문. trde_tp 기본 '3'(시장가). 지정가는 '0' + price."""
        return self._post(_URL_ORDR, "kt10000", self._order_body(stk_cd, qty, price, trde_tp))

    def sell(self, stk_cd: str, qty: int, price: int = 0, trde_tp: str = "3") -> dict:
        """kt10001 — 매도주문. 매수(kt10000)와 동일 바디 구조 (스펙 확인 완료)."""
        return self._post(_URL_ORDR, "kt10001", self._order_body(stk_cd, qty, price, trde_tp))

    def modify(
        self,
        orig_ord_no: str,
        stk_cd: str,
        mdfy_qty: int,
        mdfy_uv: int,
        mdfy_cond_uv: str = "",
    ) -> dict:
        """kt10002 — 정정주문. 미체결 주문의 수량/단가 변경.

        orig_ord_no: 정정할 원주문번호(매수/매도 응답의 7자리 ord_no).
        mdfy_qty: 정정수량(1주 단위). 0 입력 시 잔량 전부 정정.
        mdfy_uv: 정정단가(원). 응답 ord_no 는 새 주문번호.
        """
        return self._post(_URL_ORDR, "kt10002", {
            "dmst_stex_tp": "KRX",
            "orig_ord_no": orig_ord_no,
            "stk_cd": stk_cd,
            "mdfy_qty": str(mdfy_qty),
            "mdfy_uv": str(mdfy_uv),
            "mdfy_cond_uv": mdfy_cond_uv,
        })

    def cancel(self, orig_ord_no: str, stk_cd: str, cncl_qty: int = 0) -> dict:
        """kt10003 — 취소주문. 미체결 주문 취소(긴급 청산·장 마감 전 정리).

        orig_ord_no: 취소할 원주문번호(7자리).
        cncl_qty: 취소수량(1주 단위). 0(기본) 입력 시 잔량 전부 취소.
        응답 ord_no 는 새 주문번호.
        """
        return self._post(_URL_ORDR, "kt10003", {
            "dmst_stex_tp": "KRX",
            "orig_ord_no": orig_ord_no,
            "stk_cd": stk_cd,
            "cncl_qty": str(cncl_qty),
        })

    # ── 계좌 ──
    def get_balance(self, qry_tp: str = "1") -> dict:
        """kt00018 — 계좌평가잔고내역요청 (reconcile 워커가 사용). 계좌는 토큰에 귀속.

        qry_tp: 1=합산, 2=개별.
        응답 holdings 는 'acnt_evlt_remn_indv_tot' 리스트. 항목 금액·수량은 부호 포함
        0-패딩 문자열(예: '-00000000196888', rmnd_qty '000000000000003')이라
        int() 로 파싱해야 한다(앞 0·부호 그대로 int 변환 가능).
        """
        return self._post(_URL_ACNT, "kt00018", {
            "qry_tp": qry_tp,
            "dmst_stex_tp": "KRX",
        })

    def get_deposit(self, qry_tp: str = "3") -> dict:
        """kt00001 — 예수금상세현황요청. 주문 사이징(execution_engine)의 가용현금 근거.

        qry_tp: 3=추정조회, 2=일반조회.
        주요 응답: 'entr'(예수금), 'ord_alow_amt'(주문가능금액),
        'd2_entra'(d+2추정예수금). 모두 부호 포함 0-패딩 문자열 → int() 파싱.
        """
        return self._post(_URL_ACNT, "kt00001", {"qry_tp": qry_tp})

    def get_daily_realized_pnl(self, strt_dt: str, end_dt: str) -> dict:
        """ka10074 — 일자별실현손익요청. 일일 손실 한도/서킷브레이커·정산 리포트 근거.

        strt_dt/end_dt: YYYYMMDD.
        주요 응답: 'rlzt_pl'(실현손익), 'tot_buy_amt'/'tot_sell_amt', 'dt_rlzt_pl' 리스트.
        이 TR 금액은 0-패딩이 아닌 일반 문자열('474600') → int() 파싱.
        """
        return self._post(_URL_ACNT, "ka10074", {"strt_dt": strt_dt, "end_dt": end_dt})

    def get_open_orders(
        self,
        all_stk_tp: str = "0",
        trde_tp: str = "0",
        stk_cd: str = "",
        stex_tp: str = "0",
    ) -> dict:
        """ka10075 — 미체결요청. 주문 전송 후 체결/미체결 추적·정정/취소 대상 파악.

        all_stk_tp: 0=전체, 1=종목(stk_cd 지정) / trde_tp: 0=전체, 1=매도, 2=매수
        stex_tp: 0=통합, 1=KRX, 2=NXT.
        응답 'oso' 리스트: ord_no, ord_stt(주문상태), oso_qty(미체결수량),
        cntr_qty(체결량), ord_qty/ord_pric 등. 값은 +/- 부호 가능한 일반 문자열 → int().
        """
        return self._post(_URL_ACNT, "ka10075", {
            "all_stk_tp": all_stk_tp,
            "trde_tp": trde_tp,
            "stk_cd": stk_cd,
            "stex_tp": stex_tp,
        })

    def get_executions(
        self,
        qry_tp: str = "0",
        sell_tp: str = "0",
        stk_cd: str = "",
        ord_no: str = "",
        stex_tp: str = "0",
    ) -> dict:
        """ka10076 — 체결요청. 체결 내역 조회 → fill 기록·포지션 산출의 원천.

        qry_tp: 0=전체, 1=종목(stk_cd 지정) / sell_tp: 0=전체, 1=매도, 2=매수
        stex_tp: 0=통합, 1=KRX, 2=NXT.
        ord_no: 입력 주문번호보다 과거에 체결된 내역 조회(공백=전체).
        응답 'cntr' 리스트: ord_no, cntr_pric(체결가), cntr_qty(체결량),
        oso_qty(미체결수량), ord_stt(주문상태) 등. 값은 일반 문자열 → int().
        """
        return self._post(_URL_ACNT, "ka10076", {
            "stk_cd": stk_cd,
            "qry_tp": qry_tp,
            "sell_tp": sell_tp,
            "ord_no": ord_no,
            "stex_tp": stex_tp,
        })
