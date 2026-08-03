"""한국투자증권(KIS) Open API 클라이언트 — 시장 탭 선물 시세 조회 전용.

용도는 **데이터 조회**(코스피200 야간선물 등 국내선물 현재가)로 한정한다.
주문/계좌는 다루지 않는다. 토큰은 kis_token 테이블에 단일행으로 보관하며,
ensure_token() 이 DB 토큰을 재사용하고 만료 임박 시에만 재발급한다(60초 폴링 부하 최소화).

주의: REST 시세 TR(FHMIF10000000)은 **주간(정규장) 세션만** 반환한다. KRX 야간세션
시세는 REST 로 제공되지 않으며, WebSocket H0MFCNT0(야간선물 실시간체결)으로만 받는다
(workers/kis_night_futures_ws.py 가 구독해 kis_night_future 행을 갱신). approval_key 는
그 WebSocket 접속키로 get_approval_key() 가 발급한다.

REST 사양:
  - 토큰: POST /oauth2/tokenP (grant_type=client_credentials, ~24h 유효)
  - WebSocket 접속키: POST /oauth2/Approval (secretkey 필드 사용)
  - 국내선물 현재가(주간): GET /uapi/domestic-futureoption/v1/quotations/inquire-price
                     tr_id=FHMIF10000000, FID_COND_MRKT_DIV_CODE=F, FID_INPUT_ISCD=<근월물 코드>
"""
import logging
from datetime import date, datetime, timedelta

import requests

from core.config import (
    KIS_APP_KEY,
    KIS_SECRET_KEY,
    KIS_BASE_URL,
    KIS_KOSPI200_FUT_CODE,
)
from core.repository import kis_token as token_repo

logger = logging.getLogger("KisClient")

_TIMEOUT = 10
_EXPIRY_MARGIN = timedelta(minutes=5)
_FUTURES_TR_ID = "FHMIF10000000"
_FUTURES_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-price"
_INDEX_TR_ID = "FHPUP02100000"
_INDEX_PATH = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
_FUTURES_CHART_TR_ID = "FHKIF03020100"
_FUTURES_CHART_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice"
_FUTURES_MIN_TR_ID = "FHKIF03020200"
_FUTURES_MIN_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice"


def _is_token_expired(expires_dt: str | None) -> bool:
    """expires_dt(YYYY-MM-DD HH:MM:SS)가 현재시각 + 5분 이내이면 만료로 본다."""
    if not expires_dt:
        return True
    try:
        exp = datetime.strptime(expires_dt, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return datetime.now() + _EXPIRY_MARGIN >= exp


def kospi200_front_month_code() -> str:
    """코스피200 선물 근월물 KIS 단축코드 ('A01' + 연도끝자리 + MM).

    분기물(3·6·9·12월) 중 만기(2번째 목요일)가 오늘 이후인 첫 월물을 고른다.
    KIS_KOSPI200_FUT_CODE 가 .env 로 지정되면 그 값을 그대로 쓴다(강제 오버라이드).
    주간/야간 모두 동일 근월물 코드를 쓴다.
    """
    if KIS_KOSPI200_FUT_CODE:
        return KIS_KOSPI200_FUT_CODE

    today = datetime.now().date()
    quarterly = []
    for y in (today.year, today.year + 1):
        for m in (3, 6, 9, 12):
            first = date(y, m, 1)
            second_thu = date(y, m, 1 + ((3 - first.weekday()) % 7) + 7)  # 2번째 목요일
            quarterly.append((second_thu, y, m))
    quarterly.sort()
    for exp, y, m in quarterly:
        if exp >= today:
            return f"A01{y % 10}{m:02d}"
    return f"A01{today.year % 10}12"


def _to_float(val) -> float | None:
    """KIS 숫자 문자열("1,234.50", "-5") → float. 빈값/이상치는 None."""
    if val is None:
        return None
    try:
        s = str(val).replace(",", "").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _futs_candle(row: dict, time_str: str, vol_field: str) -> dict | None:
    """선물 차트 TR 의 output2 한 행 → 캔들 dict. OHLC 중 하나라도 없으면 None.

    일봉(FHKIF03020100)·분봉(FHKIF03020200) 이 컬럼명을 공유하고 거래량 필드만 다르다
    (일봉 acml_vol / 분봉 cntg_vol). 반환 shape 은 market_data.fetch_index_ohlc 와 동일.
    """
    o = _to_float(row.get("futs_oprc"))
    h = _to_float(row.get("futs_hgpr"))
    lo = _to_float(row.get("futs_lwpr"))
    c = _to_float(row.get("futs_prpr"))
    if None in (o, h, lo, c) or c == 0:
        return None
    return {
        "time": time_str,
        "open": round(o, 2), "high": round(h, 2),
        "low": round(lo, 2), "close": round(c, 2),
        "volume": _to_float(row.get(vol_field)) or 0.0,
    }


class KisRestClient:
    def __init__(self):
        self.app_key = KIS_APP_KEY
        self.secret_key = KIS_SECRET_KEY
        self.base_url = KIS_BASE_URL.rstrip("/")
        self.access_token = ""
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json; charset=UTF-8"}
        )

    # ── 인증 ──
    def get_access_token(self) -> None:
        """토큰 발급 + DB 저장 (POST /oauth2/tokenP)."""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.secret_key,
        }
        resp = self.session.post(url, json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        expires_dt = data.get("access_token_token_expired")  # "YYYY-MM-DD HH:MM:SS"
        try:
            token_repo.save_token(self.access_token, expires_dt)
        except Exception as e:
            logger.warning(f"KIS 토큰 DB 저장 실패: {e}")
        logger.info(f"KIS 토큰 발급 완료 (만료: {expires_dt or 'N/A'})")

    def get_approval_key(self) -> str:
        """WebSocket 실시간 접속키 발급 (POST /oauth2/Approval). 약 24h 유효."""
        url = f"{self.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
        }
        resp = self.session.post(url, json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["approval_key"]

    def ensure_token(self) -> None:
        """DB에서 유효 토큰을 로드. 없거나 만료 임박이면 새로 발급."""
        try:
            row = token_repo.get_token()
        except Exception as e:
            logger.warning(f"KIS 토큰 DB 조회 실패: {e}")
            row = None

        if row and row.get("access_token") and not _is_token_expired(row.get("expires_dt")):
            self.access_token = row["access_token"]
            return

        self.get_access_token()

    # ── 시세 ──
    def inquire_futures_price(self, symbol: str) -> dict | None:
        """국내선물 현재가 조회. {price, change, change_percent} 또는 None.

        야간세션(KRX 야간거래) 시간대에도 동일 근월물 코드로 야간 시세가 반영된다.
        """
        self.ensure_token()
        url = f"{self.base_url}{_FUTURES_PATH}"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.secret_key,
            "tr_id": _FUTURES_TR_ID,
            "custtype": "P",
            "Content-Type": "application/json; charset=UTF-8",
        }
        params = {"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": symbol}
        resp = self.session.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        out = data.get("output1") or {}

        price = _to_float(out.get("futs_prpr"))
        if price is None or price == 0:
            return None
        change = _to_float(out.get("futs_prdy_vrss"))
        pct = _to_float(out.get("futs_prdy_ctrt"))

        # prdy_vrss_sign: 1 상한 / 2 상승 / 3 보합 / 4 하한 / 5 하락
        sign = str(out.get("prdy_vrss_sign") or "")
        if sign in ("4", "5"):
            change = -abs(change) if change is not None else None
            pct = -abs(pct) if pct is not None else None
        elif sign in ("1", "2"):
            change = abs(change) if change is not None else None
            pct = abs(pct) if pct is not None else None

        return {
            "price": round(price, 2),
            "change": round(change, 2) if change is not None else None,
            "change_percent": round(pct, 2) if pct is not None else None,
        }

    def inquire_futures_daily_ohlc(self, symbol: str, count: int = 30) -> list[dict]:
        """국내선물 일봉 OHLCV (오래된→최신 순). 상세 차트·스파크라인 공용 원본.

        inquire-daily-fuopchartprice(FHKIF03020100) output2 를 캔들로 옮긴다. 시각은
        `YYYY-MM-DDT00:00` — 프론트 CandlestickChart 가 'T' 구분자를 요구해 일봉에도 붙인다.
        일봉은 주간·야간 세션이 합쳐진 계약 단위 값이다. 실패/무데이터면 빈 리스트.
        """
        self.ensure_token()
        url = f"{self.base_url}{_FUTURES_CHART_PATH}"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.secret_key,
            "tr_id": _FUTURES_CHART_TR_ID,
            "custtype": "P",
            "Content-Type": "application/json; charset=UTF-8",
        }
        # 거래일 기준 count개를 확보하기 위해 달력일은 넉넉히(주말·휴장 감안) 잡는다.
        end = datetime.now()
        start = end - timedelta(days=count * 2 + 15)
        params = {
            "FID_COND_MRKT_DIV_CODE": "F",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
        }
        resp = self.session.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json().get("output2") or []

        dated: list[tuple[str, dict]] = []
        for row in rows:
            d = row.get("stck_bsop_date") or ""
            candle = _futs_candle(row, f"{d[:4]}-{d[4:6]}-{d[6:]}T00:00", "acml_vol")
            if d and candle:
                dated.append((d, candle))
        dated.sort(key=lambda x: x[0])  # 날짜 오름차순(오래된→최신)
        return [c for _, c in dated][-count:]

    def inquire_futures_daily_closes(self, symbol: str, count: int = 30) -> list[float]:
        """국내선물 일별 종가 시계열 (오래된→최신 순). 카드 배경 스파크라인용."""
        return [c["close"] for c in self.inquire_futures_daily_ohlc(symbol, count)]

    def inquire_futures_minute_ohlc(self, symbol: str, max_pages: int = 1) -> list[dict]:
        """국내선물 **당일** 1분봉 OHLCV (오래된→최신 순).

        inquire-time-fuopchartprice(FHKIF03020200) 는 기준시각(FID_INPUT_HOUR_1)에서 과거로
        ~120봉만 준다. 정규장 하루(09:00~15:45 = 405분)를 채우려면 가장 오래된 봉 시각을 다음
        기준시각으로 넘기며 되짚어야 한다(max_pages=4 면 충분). 이 TR 은 당일 시초를 지나면
        **전 거래일 오후로 이어지므로**(2026-08-03 실측) 당일 봉만 모으고 거기서 멈춘다.
        max_pages 는 무한 루프 방어 상한 — 기본 1(카드 스파크라인은 최근 한 페이지면 족하다).
        실패/무데이터면 빈 리스트(호출부에서 일봉 폴백).
        """
        self.ensure_token()
        url = f"{self.base_url}{_FUTURES_MIN_PATH}"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.secret_key,
            "tr_id": _FUTURES_MIN_TR_ID,
            "custtype": "P",
            "Content-Type": "application/json; charset=UTF-8",
        }
        now = datetime.now()
        today = now.strftime("%Y%m%d")
        day_iso = f"{today[:4]}-{today[4:6]}-{today[6:]}"
        cursor_hour = now.strftime("%H%M%S")
        bars: dict[str, dict] = {}          # "HHMM" → 캔들 (페이지 겹침 방어)

        for _ in range(max(1, max_pages)):
            params = {
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_INPUT_ISCD": symbol,
                "FID_HOUR_CLS_CODE": "60",          # 60초 = 1분봉
                "FID_PW_DATA_INCU_YN": "Y",         # 과거(장 시작~) 데이터 포함
                "FID_FAKE_TICK_INCU_YN": "N",
                "FID_INPUT_DATE_1": today,          # 기준일(필수)
                "FID_INPUT_HOUR_1": cursor_hour,    # 기준시각(여기서 과거로 ~120봉)
            }
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=_TIMEOUT)
                resp.raise_for_status()
                rows = resp.json().get("output2") or []
            except Exception as e:
                logger.warning(f"선물 분봉 조회 실패({symbol} {cursor_hour}): {e}")
                break
            if not rows:
                break

            today_rows = [r for r in rows if (r.get("stck_bsop_date") or "") == today]
            added, oldest = 0, None
            for row in today_rows:
                t = (row.get("stck_cntg_hour") or "")[:4]
                if len(t) < 4:
                    continue
                candle = _futs_candle(row, f"{day_iso}T{t[:2]}:{t[2:]}", "cntg_vol")
                if not candle:
                    continue
                if t not in bars:
                    bars[t] = candle
                    added += 1
                oldest = t if oldest is None else min(oldest, t)
            # 전 거래일 구간에 닿았거나 새로 얻은 봉이 없으면(=더 되짚어도 소득 없음) 종료
            if len(today_rows) < len(rows) or not added or oldest is None:
                break
            cursor_hour = f"{oldest}00"
            if cursor_hour <= "000100":     # 자정 wrap 방어
                break
            cursor_hour = (datetime.strptime(cursor_hour, "%H%M%S")
                           - timedelta(minutes=1)).strftime("%H%M%S")

        return [bars[t] for t in sorted(bars)]

    def inquire_futures_minute_closes(self, symbol: str, count: int = 80) -> list[float]:
        """국내선물 당일 분봉 종가 시계열 (오래된→최신 순). 카드 배경 분봉 스파크라인용."""
        return [c["close"] for c in self.inquire_futures_minute_ohlc(symbol)][-count:]

    def inquire_index_price(self, index_code: str) -> dict | None:
        """국내 업종/지수 현재가 조회. {price, change, change_percent} 또는 None.

        index_code: 코스피 종합 '0001', 코스닥 종합 '1001'(KRX 업종 코드).
        REST 사양: GET /uapi/domestic-stock/v1/quotations/inquire-index-price
                   tr_id=FHPUP02100000, FID_COND_MRKT_DIV_CODE=U, FID_INPUT_ISCD=<업종코드>
        정규장 세션 기준 시세이며, 장외 시간엔 직전 종가를 반환한다.
        """
        self.ensure_token()
        url = f"{self.base_url}{_INDEX_PATH}"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.secret_key,
            "tr_id": _INDEX_TR_ID,
            "custtype": "P",
            "Content-Type": "application/json; charset=UTF-8",
        }
        params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": index_code}
        resp = self.session.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        out = data.get("output") or {}

        price = _to_float(out.get("bstp_nmix_prpr"))
        if price is None or price == 0:
            return None
        change = _to_float(out.get("bstp_nmix_prdy_vrss"))
        pct = _to_float(out.get("bstp_nmix_prdy_ctrt"))

        # prdy_vrss_sign: 1 상한 / 2 상승 / 3 보합 / 4 하한 / 5 하락
        sign = str(out.get("prdy_vrss_sign") or "")
        if sign in ("4", "5"):
            change = -abs(change) if change is not None else None
            pct = -abs(pct) if pct is not None else None
        elif sign in ("1", "2"):
            change = abs(change) if change is not None else None
            pct = abs(pct) if pct is not None else None

        return {
            "price": round(price, 2),
            "change": round(change, 2) if change is not None else None,
            "change_percent": round(pct, 2) if pct is not None else None,
        }
