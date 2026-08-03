"""
시장 데이터 서비스
- 개별 종목(시세/차트/종목명/주도주): 키움 REST API (6자리 종목코드 기준)
- 국내지수(코스피/코스닥)·선물: 한국투자증권(KIS) REST API
- 그 외 지수(미국지수·원자재·환율): yfinance
"""
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import yfinance as yf

from core.repository.ticker import lookup_name_by_ticker

logger = logging.getLogger("MarketData")


# ── 키움 데이터 서버 클라이언트 (국내 종목 시세 — lazy singleton, HTTP) ──
_kiwoom_api = None


def _get_kiwoom():
    """국내 종목 조회용 키움 HTTP 클라이언트 (lazy init). 토큰은 서버가 보장."""
    global _kiwoom_api
    if _kiwoom_api is None:
        from core.kiwoom_client import KiwoomRestClient
        _kiwoom_api = KiwoomRestClient()
    return _kiwoom_api


# ── 한국투자증권(KIS) 클라이언트 (코스피200 야간선물 시세 — lazy singleton) ──
_kis_api = None


def _get_kis():
    """선물 시세 조회용 KIS 클라이언트 (lazy init). 토큰은 클라이언트가 보장."""
    global _kis_api
    if _kis_api is None:
        from core.kis_client import KisRestClient
        _kis_api = KisRestClient()
    return _kis_api


def _kospi200_night_future() -> dict:
    """코스피200 야간선물 현재가.

    야간 WS 워커(kis_night_futures_ws)가 kis_night_future 단일행을 갱신한다.
    야간세션 중엔 실시간 체결가, 세션 종료 후엔 '마지막 야간 종가'를 다음
    세션까지 그대로 유지한다(주간선물 종가로 갈아타지 않는다 — 주간 시세는
    _kospi200_day_future 가 별도 카드로 제공).
    """
    base = {"symbol": "K200NF", "name": "코스피200 야간선물", "sparkline": None}
    none = {**base, "price": None, "change": None, "change_percent": None}
    try:
        from core.repository.kis_night_future import get_night_future
        row = get_night_future()
    except Exception:
        return none
    if not row or row.get("price") is None:
        return none
    return {
        **base,
        "price": float(row["price"]),
        "change": float(row["change_val"]) if row.get("change_val") is not None else None,
        "change_percent": float(row["change_percent"]) if row.get("change_percent") is not None else None,
    }


def _kospi200_day_future() -> dict:
    """코스피200 주간선물 현재가 (KIS REST). 주간장 중엔 실시간, 장외엔 직전 종가."""
    base = {"symbol": "K200DF", "name": "코스피200 주간선물", "sparkline": None}
    none = {**base, "price": None, "change": None, "change_percent": None}
    try:
        from core.kis_client import kospi200_front_month_code
        q = _get_kis().inquire_futures_price(kospi200_front_month_code())
    except Exception:
        return none
    if not q or q.get("price") is None:
        return none
    return {**base, **q}


def _kospi200_futures_sparkline() -> list[float] | None:
    """코스피200 선물 근월물 분봉 종가 스파크라인 (KIS REST). 당일 1분봉 우선,
    비었으면(장전·휴장 등) 일봉으로 폴백. 실패 시 None."""
    try:
        from core.kis_client import kospi200_front_month_code
        code = kospi200_front_month_code()
        kis = _get_kis()
        closes = kis.inquire_futures_minute_closes(code)
        if not closes or len(closes) < 2:
            closes = kis.inquire_futures_daily_closes(code)  # 폴백: 일봉
    except Exception:
        return None
    return closes[-80:] if closes and len(closes) >= 2 else None


# 선물 상세 차트 — 두 카드(K200NF/K200DF)가 같은 시계열을 쓰고 새로고침도 잦아 짧게 캐시한다.
# (KIS 는 연속 호출에 레이트리밋이 걸려 빈 차트가 나올 수 있다 — 2026-08-03 실측)
_FUT_CANDLE_TTL_SEC = 30
_fut_candle_cache: dict[str, dict] = {}

# 다일 구간은 거래일 수(일봉 개수)로 센다 — 야간선물 분봉 이력이 없는 과거는 일봉으로만 그린다.
_FUT_DAILY_COUNT = {"1mo": 22, "5d": 5}


def _kospi200_futures_candles(period: str) -> list[dict]:
    """코스피200 근월물 **연속** 캔들 — 주간·야간을 한 시계열로. 상세 차트(K200NF/K200DF 공용).

    두 카드는 같은 근월물 계약의 다른 세션이라 차트도 하나로 잇는 게 맞다. 종가베팅이
    실제로 노출되는 구간(주간 종가 → 야간 → 익일 시가)이 한 화면에 보인다.
      · period "1d" → 1분봉: 어젯밤 야간세션(DB kis_night_future_bar) + 오늘 주간세션(KIS 분봉).
        야간 봉은 extended=True 로 표시해 차트가 흐리게 그린다.
      · 그 외      → 일봉(KIS): 야간선물 분봉 이력은 2026-08-03 부터라 그 이전은 일봉만 가능하다.
    실패 시 빈 리스트(차트가 '데이터 없음' 표시).
    """
    from core.kis_client import kospi200_front_month_code

    cached = _fut_candle_cache.get(period)
    now_ts = time.time()
    if cached and now_ts - cached["at"] < _FUT_CANDLE_TTL_SEC:
        return cached["data"]

    try:
        code = kospi200_front_month_code()
        kis = _get_kis()
    except Exception as e:
        logger.warning(f"선물 근월물/클라이언트 준비 실패: {e}")
        return []

    candles: list[dict] = []
    if period != "1d":
        try:
            candles = kis.inquire_futures_daily_ohlc(
                code, count=_FUT_DAILY_COUNT.get(period, 22))
        except Exception as e:
            logger.warning(f"선물 일봉 조회 실패({period}): {e}")
    else:
        # 야간세션은 전날 18:00 에 열려 당일 05:05 에 닫힌다 → 전날 18:00 부터 긁는다.
        night_start = (datetime.now() - timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0)
        try:
            from core.repository.kis_night_future_bar import get_bars
            for b in get_bars(night_start):
                candles.append({
                    "time": b["bar_time"].strftime("%Y-%m-%dT%H:%M"),
                    "open": float(b["open"]), "high": float(b["high"]),
                    "low": float(b["low"]), "close": float(b["close"]),
                    "volume": 0.0,      # 야간 체결량은 WS 에서 수집하지 않는다
                    "extended": True,   # 야간세션 — 차트에서 흐리게
                })
        except Exception as e:
            logger.warning(f"야간선물 분봉 조회 실패: {e}")
        try:
            # 정규장 405분(09:00~15:45)을 덮으려면 페이지당 ~120봉 × 4
            candles.extend(kis.inquire_futures_minute_ohlc(code, max_pages=4))
        except Exception as e:
            logger.warning(f"주간선물 분봉 조회 실패: {e}")
        candles.sort(key=lambda c: c["time"])

    if candles:                 # 실패(빈 결과)는 캐시하지 않는다 — 다음 요청에서 재시도
        _fut_candle_cache[period] = {"at": now_ts, "data": candles}
    return candles


def _parse_num(val) -> float:
    """키움 응답 가격 문자열("+53,500", "-1200") → float. 빈값/이상치는 0."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("+", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _norm_code(ticker: str) -> str:
    """'005930.KS', '005930_NX' 등 잔여 접미사가 있어도 6자리 코드만 추출"""
    return (ticker or "").split(".")[0].split("_")[0].strip()


# ── 시장 지수 정의 ──

MARKET_INDICES = {
    "US": [
        {"symbol": "^GSPC", "name": "S&P 500"},
        {"symbol": "^IXIC", "name": "NASDAQ"},
        {"symbol": "^DJI", "name": "다우존스"},
        {"symbol": "^SOX", "name": "필라델피아 반도체"},
        {"symbol": "^VIX", "name": "VIX (공포지수)"},
        {"symbol": "DX-Y.NYB", "name": "달러 인덱스"},
    ],
    # 코스피/코스닥은 KIS REST(아래 KIS_INDICES)에서 조회해 그룹 앞에 합류.
    # 환율·EWY·KORU는 yfinance(미국 상장 한국 ETF, 전날 미국장 반응 참고용).
    "KR": [
        {"symbol": "USDKRW=X", "name": "원/달러 환율"},
        {"symbol": "SKHY", "name": "SK하이닉스 ADR (SKHY)"},
        {"symbol": "EWY", "name": "MSCI 한국 ETF (EWY)"},
        {"symbol": "KORU", "name": "한국 3배 레버리지 ETF (KORU)"},
    ],
    "COMMODITIES": [
        {"symbol": "GC=F", "name": "금"},
        {"symbol": "CL=F", "name": "WTI 원유"},
        {"symbol": "BTC-USD", "name": "비트코인"},
    ],
    # 종가베팅 전 '내일 한국장 갭' 참고 지표.
    # 나스닥100 선물(NQ=F)은 yfinance, 코스피200 야간선물은 KIS REST(아래 병합)에서 조회한다.
    "FUTURES": [
        {"symbol": "NQ=F", "name": "나스닥100 선물"},
    ],
}

# 국내 지수 — KIS 국내업종 현재가(FID_INPUT_ISCD 업종코드)로 조회. KR 그룹 맨 앞에 합류.
KIS_INDICES = [
    {"symbol": "^KS11", "name": "코스피", "index_code": "0001"},
    {"symbol": "^KQ11", "name": "코스닥", "index_code": "1001"},
]

# yfinance에 시계열이 없는 커스텀 심볼(코스피200 선물) — 배경 스파크라인 미제공.
# yfinance 시계열이 없는 커스텀 심볼 — 카드 미니 스파크라인은 KIS 쪽에서 따로 채운다.
_NO_SPARKLINE_SYMBOLS = {"K200NF", "K200DF"}
# 상세 차트는 KIS(주간)+DB(야간)로 조립 — _kospi200_futures_candles
_FUTURES_CHART_SYMBOLS = {"K200NF", "K200DF"}

# 심볼 → 표시명 (상세 페이지·히스토리 응답에서 사용). 커스텀 선물명도 포함.
_INDEX_NAMES = {
    **{it["symbol"]: it["name"] for group in MARKET_INDICES.values() for it in group},
    **{it["symbol"]: it["name"] for it in KIS_INDICES},
    "K200NF": "코스피200 야간선물",
    "K200DF": "코스피200 주간선물",
}


def resolve_index_name(symbol: str) -> str:
    """지수/심볼 표시명. 정의에 없으면 심볼 그대로 반환."""
    return _INDEX_NAMES.get(symbol, symbol)


def _kis_index_quote(item: dict) -> dict:
    """국내 지수(코스피/코스닥) 현재가 (KIS REST). 장중 실시간, 장외엔 직전 종가.

    배경 스파크라인은 yfinance(^KS11/^KQ11) 일봉으로 별도 조회한다.
    """
    base = {"symbol": item["symbol"], "name": item["name"]}
    sparkline = _fetch_sparkline(item["symbol"])
    none = {**base, "price": None, "change": None, "change_percent": None, "sparkline": sparkline}
    try:
        q = _get_kis().inquire_index_price(item["index_code"])
    except Exception:
        return none
    if not q or q.get("price") is None:
        return none
    return {**base, **q, "sparkline": sparkline}

def _safe_float(val) -> float | None:
    """nan/inf를 None으로 변환하여 JSON 직렬화 안전하게 처리"""
    if val is None:
        return None
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


def _closes_to_sparkline(hist, keep: int = 80) -> list[float] | None:
    """종가 시계열 → 카드 배경 스파크라인용 float 리스트 (최근 keep개)."""
    try:
        closes = [_safe_float(c) for c in hist["Close"].tolist()]
    except Exception:
        return None
    closes = [c for c in closes if c is not None]
    return closes[-keep:] if len(closes) >= 2 else None


def _fetch_sparkline(symbol: str) -> list[float] | None:
    """yfinance 분봉(최근 1거래일 5분봉, 프리·애프터 포함) 종가 스파크라인.

    상세 차트와 동일하게 카드 미니 스파크라인도 분봉으로 그린다. 분봉이 빈 심볼(장이 오래
    닫혀 최근 세션이 없는 경우 등)은 일봉(1개월)으로 폴백한다. 커스텀 심볼/실패 시 None."""
    if symbol in _NO_SPARKLINE_SYMBOLS:
        return None
    try:
        hist = yf.Ticker(symbol).history(period="1d", interval="5m", prepost=True)
        if hist is None or hist.empty:
            hist = yf.Ticker(symbol).history(period="1mo")  # 폴백: 일봉
        if hist is None or hist.empty:
            return None
        return _closes_to_sparkline(hist)
    except Exception:
        return None


def fetch_index_ohlc(symbol: str, period: str = "5d", interval: str = "5m",
                     prepost: bool = True) -> list[dict]:
    """시장 지수/심볼의 OHLCV 시계열 (yfinance). 상세 페이지 분봉 차트용.

    분봉(intraday) + 프리/애프터마켓 포함이 기본. `prepost=True` 면 정규장 밖(프리·애프터)
    체결도 한 시계열에 합쳐 반환한다(주식/ETF 만 실제 확장봉 존재; 지수·환율은 무영향).
    시각은 전 심볼을 **KST(Asia/Seoul)** 로 변환한 벽시계값 문자열로 낸다 — 차트는 이 값을
    그대로 시각 축에 표시한다(US 정규장 09:30~16:00 ET → 22:30~05:00 KST 처럼 한국 시간축 통일).

    반환: [{time:"YYYY-MM-DDTHH:MM", open, high, low, close, volume, extended}, ...] (오름차순).
      extended=True 는 정규장 밖(프리/애프터) 봉. 코스피/코스닥(^KS11/^KQ11)도 yfinance 시계열
      을 쓴다(카드 라이브값은 KIS). 조회 실패 시 [].

    코스피200 선물(K200NF/K200DF)은 yfinance 에 없어 KIS+DB 로 따로 조립한다
    (_kospi200_futures_candles — 주간·야간 연속, 야간 봉이 extended=True)."""
    if symbol in _FUTURES_CHART_SYMBOLS:
        return _kospi200_futures_candles(period)
    if symbol in _NO_SPARKLINE_SYMBOLS:
        return []
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period=period, interval=interval, prepost=prepost)
    except Exception:
        return []
    if hist is None or hist.empty:
        return []
    # 정규장 시간대 판정용 — yfinance metadata(있으면). 없으면 extended 전부 False(무해).
    reg_start = reg_end = None
    try:
        meta = getattr(tk, "history_metadata", None) or {}
        gmt = meta.get("gmtoffset")
        cts = meta.get("currentTradingPeriod") or {}
        reg = cts.get("regular") or {}
        if gmt is not None and reg.get("start") and reg.get("end"):
            # epoch(UTC) + gmtoffset → 거래소 로컬 초(자정 기준 hh:mm 비교용)
            reg_start = ((reg["start"] + gmt) % 86400)
            reg_end = ((reg["end"] + gmt) % 86400)
    except Exception:
        reg_start = reg_end = None
    candles: list[dict] = []
    for idx, row in hist.iterrows():
        o = _safe_float(row.get("Open"))
        h = _safe_float(row.get("High"))
        low = _safe_float(row.get("Low"))
        c = _safe_float(row.get("Close"))
        if None in (o, h, low, c):
            continue
        # extended(정규장 밖) 판정은 거래소 로컬(idx 자체 tz) 기준 — 세션 시간과 맞아야 정확.
        extended = False
        if reg_start is not None:
            sec = idx.hour * 3600 + idx.minute * 60
            extended = not (reg_start <= sec < reg_end)
        # 표시 시각은 KST 로 변환(tz-naive 면 그대로) — 전 심볼을 한국 시간축으로 통일.
        try:
            disp = idx.tz_convert("Asia/Seoul")
        except (TypeError, AttributeError):
            disp = idx
        candles.append({
            "time": disp.strftime("%Y-%m-%dT%H:%M"),
            "open": o, "high": h, "low": low, "close": c,
            "volume": _safe_float(row.get("Volume")) or 0.0,
            "extended": extended,
        })
    return candles


def _fetch_quote(item: dict) -> dict:
    """하나의 종목/지수 데이터를 yfinance에서 조회 (배경 스파크라인 포함)"""
    empty = {**item, "price": None, "change": None, "change_percent": None, "sparkline": None}
    try:
        stock = yf.Ticker(item["symbol"])
        hist = stock.history(period="1mo")
        if hist.empty:
            return empty
        current = _safe_float(hist["Close"].iloc[-1])
        if current is None:
            return empty
        # 가격·일일 등락은 일봉(hist) 기준 그대로, 미니 스파크라인만 분봉으로.
        sparkline = _fetch_sparkline(item["symbol"])
        prev = _safe_float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        if prev is None or prev == 0:
            return {**item, "price": current, "change": None, "change_percent": None, "sparkline": sparkline}
        change = round(current - prev, 2)
        change_pct = round((change / prev) * 100, 2)
        return {
            **item,
            "price": current,
            "change": change,
            "change_percent": change_pct,
            "sparkline": sparkline,
        }
    except Exception:
        return empty


def _kiwoom_quote(code: str) -> dict:
    """키움 ka10001 기준 실시간 현재가/등락 (실패 시 None)"""
    none = {"price": None, "change": None, "change_percent": None}
    try:
        info = _get_kiwoom().get_stock_basic_info(code)
    except Exception:
        return none
    cur = abs(_parse_num(info.get("cur_prc")))
    if cur == 0:
        return none
    pct = _parse_num(info.get("flu_rt"))
    chg = _parse_num(info.get("pred_pre"))
    # flu_rt가 비어있으면 전일대비(pred_pre)로 등락률 산출
    if pct == 0 and chg != 0:
        prev = cur - chg
        if prev:
            pct = chg / prev * 100
    return {
        "price": cur,
        "change": round(chg, 2),
        "change_percent": round(pct, 2),
    }


def _kiwoom_price_on_date(code: str, ticker: str, date: str) -> dict:
    """키움 ka10081 일봉으로 특정 일자 종가 + 전 거래일 대비 등락률 조회"""
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "잘못된 날짜 형식입니다."}

    try:
        data = _get_kiwoom().get_daily_chart(code, dt=target.strftime("%Y%m%d"))
        candles = data.get("stk_dt_pole_chart_qry", [])
    except Exception:
        return {"error": "데이터를 찾을 수 없습니다."}

    tgt = target.strftime("%Y%m%d")
    rows = sorted(
        [c for c in candles if c.get("dt") and c["dt"] <= tgt],
        key=lambda c: c["dt"], reverse=True,
    )
    if not rows:
        return {"error": "데이터를 찾을 수 없습니다."}

    close = abs(_parse_num(rows[0].get("cur_prc")))
    if close == 0:
        return {"error": "데이터를 찾을 수 없습니다."}

    if len(rows) >= 2:
        prev = abs(_parse_num(rows[1].get("cur_prc")))
        change = round(close - prev, 2) if prev else 0.0
        change_percent = round(change / prev * 100, 2) if prev else 0.0
    else:
        change = 0.0
        change_percent = 0.0

    return {
        "ticker": ticker,
        "price": close,
        "change": change,
        "change_percent": change_percent,
    }


def fetch_stock_price(ticker: str, date: str | None = None) -> dict:
    """개별 종목 주가 및 등락률 조회 (키움 REST API).

    date 미지정 시 실시간 가격, 지정 시 해당 일자 종가와 전 거래일 대비 등락률.
    """
    code = _norm_code(ticker)
    if not code:
        return {"error": "데이터를 찾을 수 없습니다."}

    if date:
        return _kiwoom_price_on_date(code, ticker, date)

    q = _kiwoom_quote(code)
    if q["price"] is None:
        return {"error": "데이터를 찾을 수 없습니다."}
    return {"ticker": ticker, **q}


def fetch_stock_history(ticker: str, period: str = "7d") -> list[dict]:
    """최근 주가 히스토리 (차트 오버레이용, 키움 일봉)"""
    code = _norm_code(ticker)
    if not code:
        return []
    count = int(re.sub(r"\D", "", period) or "7")

    try:
        data = _get_kiwoom().get_daily_chart(code)
        candles = data.get("stk_dt_pole_chart_qry", [])
    except Exception:
        return []

    rows = sorted(
        [c for c in candles if c.get("dt")],
        key=lambda c: c["dt"], reverse=True,
    )[:count]

    result = []
    for c in reversed(rows):
        dt = c["dt"]
        result.append({
            "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
            "price": abs(_parse_num(c.get("cur_prc"))),
        })
    return result


def fetch_stock_name(ticker: str) -> str:
    """티커로 종목명 조회 (dictionary → 키움 순서, 국장 전용)"""
    original_ticker = ticker
    ticker = (ticker or "").strip().upper()

    # 1) ticker_dictionary에서 우선 조회
    dict_name = lookup_name_by_ticker(ticker)
    if dict_name:
        return dict_name

    code = _norm_code(ticker)
    if not re.match(r"^\d{6}$", code):
        return original_ticker

    # 2) 키움 ka10001 폴백
    try:
        info = _get_kiwoom().get_stock_basic_info(code)
        name = (info.get("stk_nm") or "").strip()
        if name:
            return name
    except Exception:
        pass

    return original_ticker


def fetch_market_indices() -> dict:
    """주요 시장 지수 일괄 조회 (카테고리별 그룹핑)"""
    all_items = []
    for items in MARKET_INDICES.values():
        all_items.extend(items)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_fetch_quote, all_items))

    grouped = {}
    idx = 0
    for category, items in MARKET_INDICES.items():
        grouped[category] = results[idx : idx + len(items)]
        idx += len(items)

    # 코스피·코스닥(KIS REST)을 KR 그룹 맨 앞에 합류 — 환율만 yfinance.
    grouped["KR"] = [_kis_index_quote(it) for it in KIS_INDICES] + grouped.get("KR", [])

    # 코스피200 야간선물(마지막 야간 종가 유지) + 주간선물(실시간 REST)을
    # 선물 섹션 맨 앞에 합류 — 국장 시초가에 가장 직접적.
    # 배경 스파크라인은 KIS 선물 일봉(근월물)에서 한 번만 받아 두 카드에 공유한다
    # (야간/주간 모두 동일 근월물 계약이라 일별 추세는 같다).
    fut_night = _kospi200_night_future()
    fut_day = _kospi200_day_future()
    fut_spark = _kospi200_futures_sparkline()
    if fut_spark:
        fut_night["sparkline"] = fut_spark
        fut_day["sparkline"] = fut_spark
    grouped["FUTURES"] = [fut_night, fut_day] + grouped.get("FUTURES", [])

    return grouped


# ── 엣지 연구용 시장 스냅샷 (market_snapshot 테이블 1행) ──

def fetch_edge_market_snapshot() -> dict:
    """일 단위 시장 피처 한 세트 조회 — market_snapshot 컬럼과 1:1 대응(F2·레짐 연구용).

    기존 표시용 조회 경로를 그대로 재사용한다: 미국·환율은 yfinance(_fetch_quote),
    국내 지수는 KIS(inquire_index_price), 코스피200 선물은 주간/야간 헬퍼.
    개별 실패 항목은 None(그 지표만 제외, 나머지는 계속). vix 는 등락률이 아닌 지수 값.
    """
    yf_items = [
        {"symbol": "NQ=F", "name": "NQ"},
        {"symbol": "^GSPC", "name": "SPX"},
        {"symbol": "^SOX", "name": "SOX"},
        {"symbol": "^VIX", "name": "VIX"},
        {"symbol": "USDKRW=X", "name": "USDKRW"},
        {"symbol": "CL=F", "name": "WTI"},
        {"symbol": "EWY", "name": "EWY"},
        {"symbol": "KORU", "name": "KORU"},
        {"symbol": "SKHY", "name": "SKHY"},
    ]
    with ThreadPoolExecutor(max_workers=9) as executor:
        q = list(executor.map(_fetch_quote, yf_items))
    nq, spx, sox, vix, usdkrw, wti, ewy, koru, skhy = q

    def _kis_index_pct(index_code: str) -> float | None:
        try:
            quote = _get_kis().inquire_index_price(index_code)
            return quote.get("change_percent") if quote else None
        except Exception:
            return None

    return {
        "kospi_ret": _kis_index_pct("0001"),
        "kosdaq_ret": _kis_index_pct("1001"),
        "nq_fut_ret": nq.get("change_percent"),
        "spx_ret": spx.get("change_percent"),
        "sox_ret": sox.get("change_percent"),
        "vix": vix.get("price"),
        "usdkrw_ret": usdkrw.get("change_percent"),
        "wti_ret": wti.get("change_percent"),
        "ewy_ret": ewy.get("change_percent"),
        "koru_ret": koru.get("change_percent"),
        "skhy_ret": skhy.get("change_percent"),
        "k200f_day_ret": _kospi200_day_future().get("change_percent"),
        "k200f_night_ret": _kospi200_night_future().get("change_percent"),
    }


# ── 미국 세션 확장(프리/애프터) 프록시 — 종가베팅 매수 게이트/아침 손절 강화용 ──
# 종가베팅은 오후에 사서 익일 국장 시가까지 오버나잇 홀드한다. 익일 갭을 미리 읽으려면
# "매수 시점 이후~국장 개장 전"의 미국 움직임이 필요한데, 미국 정규장 '일일 등락'은 지난밤
# 세션이라 이미 우리 종가에 반영돼 있다. 그래서 여기선 두 가지를 함께 노출한다:
#   · regular_ret  : 직전 정규장 종가 등락률(= 지난밤 세션 결과). 아침(monitor 08시대)에 오버나잇
#                    US 결과로 그날 보유분 손절을 보수적으로 조일 때 쓴다.
#   · extended_ret : 프리/애프터마켓 최근 등락률(정규장 종가 대비). NXT 매수(19:50=미국 프리마켓
#                    열림) 시점의 '장 마감 후 최근 등락' — 매수 게이트의 순방향 신호.
# 심볼: 반도체(SOXX·SK하이닉스 ADR SKHY) + 한국(EWY·KORU 3x). NQ 선물과 중복 아닌 섹터/국가 축.
US_EXTENDED_SYMBOLS = ["SOXX", "SKHY", "EWY", "KORU"]
_US_EXT_TTL_SEC = 60
_us_ext_cache: dict = {"at": 0.0, "data": None}


def _us_extended_one(symbol: str) -> dict:
    """한 US 심볼의 정규장 등락 + 장 마감 후(프리/애프터) 최근 등락 + 시장 상태.

    실패·필드 부재는 None(그 심볼만 제외, 소비자는 None 이면 그 축 미개입).
    프리마켓이 살아있으면 extended_ret=프리마켓 등락(신선), 폐장이면 마지막 애프터마켓 등락.
    """
    out = {"symbol": symbol, "regular_ret": None, "extended_ret": None, "market_state": None}
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return out
    out["market_state"] = info.get("marketState")
    prev = info.get("regularMarketPreviousClose")
    reg = info.get("regularMarketPrice")
    if prev and reg is not None:
        out["regular_ret"] = round((reg - prev) / prev * 100, 3)
    # 장 마감 후 최근 등락: 프리마켓 우선(신선), 없으면 애프터마켓 — 정규장 종가(reg) 대비로 직접
    # 계산한다(yfinance *ChangePercent 필드의 fraction/percent 단위 모호성 회피).
    ext_price = info.get("preMarketPrice")
    if ext_price is None:
        ext_price = info.get("postMarketPrice")
    if ext_price is not None and reg:
        out["extended_ret"] = round((float(ext_price) - reg) / reg * 100, 3)
    return out


def fetch_us_extended() -> dict:
    """US_EXTENDED_SYMBOLS 각각의 정규장/확장시간 등락 스냅샷 {symbol: {...}}. 60s TTL 캐시."""
    now = time.time()
    if _us_ext_cache["data"] is not None and now - _us_ext_cache["at"] < _US_EXT_TTL_SEC:
        return _us_ext_cache["data"]
    with ThreadPoolExecutor(max_workers=len(US_EXTENDED_SYMBOLS)) as ex:
        rows = list(ex.map(_us_extended_one, US_EXTENDED_SYMBOLS))
    data = {r["symbol"]: r for r in rows}
    _us_ext_cache.update(at=now, data=data)
    return data
