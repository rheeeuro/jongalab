"""KRX 야간선물 실시간 시세 WebSocket 워커.

평일 18:00 PM2 cron 으로 기동(야간세션 18:00~익일 05:00). KIS WebSocket
H0MFCNT0(KRX 야간선물 실시간체결)을 구독해 코스피200 근월물 야간 체결가를 두 곳에 쓴다:
  1) kis_night_future 단일행 — **현재가**(표시·futures_gate 소비). 기존과 동일.
  2) kis_night_future_bar 1분봉 — **이력**(append-only). 단일행은 덮어쓰기라 시계열이 남지
     않아, 매수 시점 '변화율(모멘텀)' 축 검증도 야간 급변 사후 분석도 불가능했다(sql/46 참고).
05:05 KST(세션 종료)에 자체 종료한다. 주간↔야간 표시 전환은 core.market_data 가 단일행의
신선도(updated_at)로 판단하므로, 이 워커는 '세션 동안 체결을 흘려넣는' 역할만 한다.

데이터 포맷(H0MFCNT0 체결, '^' 구분): [0]종목코드 [1]체결시각 [2]전일대비
[3]전일대비부호(1상한2상승3보합4하한5하락) [4]전일대비율 [5]현재가 ...
"""
import asyncio
import json
import logging
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import websockets

from core.logging_setup import setup_logging
from core.config import KIS_WS_URL
from core.kis_client import KisRestClient, kospi200_front_month_code, _to_float
from core.repository.kis_night_future import save_night_future
from core.repository.kis_night_future_bar import save_bar

setup_logging()
logger = logging.getLogger("KisNightFuturesWS")

KST = ZoneInfo("Asia/Seoul")
_TR_ID = "H0MFCNT0"
_SESSION_END = dtime(5, 5)        # 05:05 KST 종료
_DAY_GUARD = dtime(17, 0)         # 17:00~05:05 사이는 '세션 외'로 간주
_WRITE_MIN_INTERVAL = 2.0         # DB 쓰기 최소 간격(초)
_RECV_TIMEOUT = 30                # 한산한 구간 대비 recv 타임아웃(초)


def _outside_session() -> bool:
    """현재 KST 가 야간세션 시간대 밖(05:05~17:00)이면 True."""
    now = datetime.now(KST).time()
    return _SESSION_END <= now < _DAY_GUARD


def _parse_tick(msg: str):
    """H0MFCNT0 체결 메시지 → (price, change, change_pct, quote_time) 또는 None."""
    parts = msg.split("|")
    if len(parts) < 4:
        return None
    f = parts[3].split("^")
    if len(f) < 6:
        return None
    quote_time = f[1]
    change = _to_float(f[2])
    sign = f[3]
    pct = _to_float(f[4])
    price = _to_float(f[5])
    if price is None or price == 0:
        return None
    if sign in ("4", "5"):  # 하한/하락
        change = -abs(change) if change is not None else None
        pct = -abs(pct) if pct is not None else None
    return price, change, pct, quote_time


class _BarBuilder:
    """체결 틱 → 1분봉 집계기. 분이 바뀌는 순간 직전 봉을 append 한다.

    체결이 없는 분은 봉을 만들지 않는다(빈 봉 생략). 그래야 '유동성이 비어 있던 구간'이
    데이터에 그대로 남아 사후 분석에서 보간과 구분된다. 분 버킷은 로컬 KST 시계 기준이다
    — 실시간 스트림이라 거래소 체결시각과 사실상 같고, 자정을 넘는 야간세션에서 날짜를
    직접 조립할 필요가 없다(체결시각 필드는 HHMMSS 라 날짜가 없다).
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._minute: datetime | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._pct: float | None = None
        self._prev_close: float | None = None
        self._ticks = 0

    def add(self, price: float, change: float | None, pct: float | None) -> None:
        minute = datetime.now(KST).replace(second=0, microsecond=0, tzinfo=None)
        if self._minute is not None and minute != self._minute:
            self.flush()
        if self._minute is None or minute != self._minute:
            self._minute = minute
            self._o = self._h = self._l = price
            self._ticks = 0
        self._h = max(self._h, price)
        self._l = min(self._l, price)
        self._c = price
        self._pct = pct
        # 전일(주간 정산가) = 현재가 − 전일대비. 등락률 분모를 사후에 재계산할 수 있게 남긴다.
        self._prev_close = round(price - change, 2) if change is not None else None
        self._ticks += 1

    def flush(self) -> None:
        """진행 중인 봉을 확정 저장. 저장 실패는 경고만 남기고 스트림을 죽이지 않는다."""
        if self._minute is None or self._ticks == 0:
            return
        try:
            save_bar(self.symbol, self._minute, self._o, self._h, self._l, self._c,
                     self._pct, self._prev_close, self._ticks)
        except Exception as e:
            logger.warning(f"분봉 저장 실패({self._minute:%H:%M}): {e}")
        self._minute = None
        self._ticks = 0


async def _stream(approval_key: str, symbol: str, bar: "_BarBuilder") -> None:
    """WS 연결 1회 — 세션 종료 시각까지 체결을 받아 DB 갱신."""
    sub = {
        "header": {"approval_key": approval_key, "custtype": "P",
                   "tr_type": "1", "content-type": "utf-8"},
        "body": {"input": {"tr_id": _TR_ID, "tr_key": symbol}},
    }
    async with websockets.connect(KIS_WS_URL, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps(sub))
        logger.info(f"구독 시작: {_TR_ID} / {symbol}")
        loop = asyncio.get_running_loop()
        last_write = 0.0
        while True:
            if _outside_session():
                logger.info("야간세션 종료 시각 — 스트림 종료")
                bar.flush()   # 마지막 미완성 봉도 남긴다
                return
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=_RECV_TIMEOUT)
            except asyncio.TimeoutError:
                continue  # 체결 한산 — 세션 체크 후 계속
            if not msg:
                continue
            if msg[0] not in ("0", "1"):
                # 제어 메시지: PINGPONG 은 그대로 되돌려준다(연결 유지)
                if "PINGPONG" in msg:
                    await ws.send(msg)
                continue
            parsed = _parse_tick(msg)
            if not parsed:
                continue
            price, change, pct, qtime = parsed
            # 분봉은 전 체결을 집계한다(고가/저가가 샘플링에 깎이지 않게). 단일행 현재가만
            # 쓰기 간격 제한을 둔다 — 표시용이라 초당 수 회 갱신할 이유가 없다.
            bar.add(price, change, pct)
            now = loop.time()
            if now - last_write >= _WRITE_MIN_INTERVAL:
                try:
                    save_night_future(symbol, price, change, pct, qtime)
                    last_write = now
                except Exception as e:
                    logger.warning(f"DB 저장 실패: {e}")


async def _run() -> None:
    if _outside_session():
        logger.info("야간세션 시간대가 아님 — 종료")
        return
    client = KisRestClient()
    approval_key = client.get_approval_key()
    symbol = kospi200_front_month_code()
    bar = _BarBuilder(symbol)
    # 세션 동안 연결이 끊기면 재연결한다.
    while not _outside_session():
        try:
            await _stream(approval_key, symbol, bar)
        except Exception as e:
            logger.warning(f"WS 연결 끊김/오류: {e} — 5초 후 재연결")
            bar.flush()   # 끊긴 시점까지 모인 봉을 잃지 않는다(재접속 시 같은 분이면 병합)
            await asyncio.sleep(5)
            try:
                approval_key = client.get_approval_key()  # 접속키 만료 대비 재발급
            except Exception:
                pass


def main() -> int:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger.error(f"야간선물 WS 워커 오류: {e}")
        return 1
    logger.info("야간선물 WS 워커 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
