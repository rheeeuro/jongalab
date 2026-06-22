"""KRX 야간선물 실시간 시세 WebSocket 워커.

평일 18:00 PM2 cron 으로 기동(야간세션 18:00~익일 05:00). KIS WebSocket
H0MFCNT0(KRX 야간선물 실시간체결)을 구독해 코스피200 근월물 야간 체결가를
kis_night_future 단일행에 갱신한다. 05:05 KST(세션 종료)에 자체 종료한다.
주간↔야간 표시 전환은 core.market_data 가 행의 신선도(updated_at)로 판단하므로,
이 워커는 '야간세션 동안 최신 체결가를 단일행에 흘려넣는' 역할만 한다.

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


async def _stream(approval_key: str, symbol: str) -> None:
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
    # 세션 동안 연결이 끊기면 재연결한다.
    while not _outside_session():
        try:
            await _stream(approval_key, symbol)
        except Exception as e:
            logger.warning(f"WS 연결 끊김/오류: {e} — 5초 후 재연결")
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
