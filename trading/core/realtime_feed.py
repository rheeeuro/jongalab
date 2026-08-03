"""키움 REST API WebSocket 실시간 피드 — 시세(0B 주식체결) + 주문체결통보(00) + 수급 관측(0w). 읽기 전용 구독.

폴링을 대체하는 목적은 두 가지다:
  1) **손절 지연 제거** — 15초 폴링은 노이즈를 필터하는 게 아니라 무작위로 샘플링한다.
     진짜 하락이면 손절선보다 낮은 가격에 팔리고(확실한 손실), 순간 급락이면 운에 맡긴다.
     틱마다 판정하면 손절선에 붙은 가격에 나간다. (2026-07-18 백테스트에서 '확인틱'=지연 추가가
     현행보다 나빴던 것과 같은 방향 — 그 백테스트는 1분봉이라 15초/1초를 구분하지 못했다.)
  2) **REST 부하 제거** — 정규장 밖 `get_market_price` 는 종목당 ka10100+ka10081 2콜(≈0.4s)이다.
     보유 10종목이면 15초마다 20콜. WS 는 구독 후 0콜.

⚠️ 이 피드는 **항상 옵셔널**이다. 연결 실패·틱 없음·값 오래됨(TTL) 이면 호출부가 기존 REST
경로로 폴백해야 한다. WS 가 죽어도 현행 동작과 동일하게 돌아가는 것이 설계 요구사항이다
(조용히 끊긴 WS 의 stale 가격으로 손절이 미발동하는 것이 최악의 실패 모드).

프로토콜(실측 확인 2026-07-31):
  접속   wss://api.kiwoom.com:10000/api/dostk/websocket
  로그인 {"trnm":"LOGIN","token":"<kiwoom 공유 access_token>"} → {"trnm":"LOGIN","return_code":0}
  등록   {"trnm":"REG","grp_no":"1","refresh":"1","data":[{"item":[...],"type":["0B"]}]}
         · item 은 KRX 는 종목코드, NXT 는 `{코드}_NX`
         · 주문체결통보(00)는 계정 단위 — item 은 [""] 로 별도 grp_no 등록
  PING   수신값을 그대로 되돌려준다(연결 유지)
  틱     {"trnm":"REAL","data":[{"type":"0B","item":"000660","values":{...}}]}
         values: "10" 현재가(±부호) · "20" 체결시각(HHMMSS) · "9081" 거래소(KRX|NXT)

수급 관측(2026-08-03, `SUPPLY_FEED_ENABLED`) — **판정에 쓰지 않는 수집 전용 축**이다.
0B 틱에 이미 체결강도·매수/매도 체결량이 실려 오고(추가 구독 0), 프로그램 순매수는 0w 를
별도 그룹으로 구독해 받는다. 이 축은 과거 데이터가 없어(ka90008 은 date 를 무시하고 당일치만
반환) 백테스트가 불가능해서, 먼저 쌓고 나중에 검증한다. 값이 없거나 낡아도 손절·스탑은 무영향.
"""
import json
import logging
import threading
import time

from core.config import (
    KIWOOM_WS_URL,
    KIWOOM_WS_MOCK_URL,
    KIWOOM_USE_MOCK,
    REALTIME_TTL_SEC,
    SUPPLY_FEED_ENABLED,
)
from core.kiwoom_data_client import to_int
from core.repository import kiwoom_token as token_repo

logger = logging.getLogger("RealtimeFeed")

_TYPE_TRADE = "0B"        # 주식체결(시세)
_TYPE_FILL = "00"         # 주문체결통보(계정 단위)
_TYPE_PROGRAM = "0w"      # 종목별프로그램매매(수급 관측 — 판정 미사용)

# 수급 관측 필드(2026-08-03 실측 탐침). **판정에 쓰지 않는다** — audit_log 수집 전용.
#   0B 는 이미 구독 중이라 추가 비용 0. 필드 의미는 산술 교차검증으로 확정했다:
#     체결강도(228) == 매수체결량(1031)/매도체결량(1030)*100  (삼성 78.13, NXT 53.60 일치)
#     매수비율(1032) == 1031/(1030+1031)                      (43.86 / 34.90 일치, 음수=매도우위)
_FIELDS_TRADE = {"228": "cntr_str", "1030": "sell_qty", "1031": "buy_qty", "1032": "buy_ratio"}
#   0w 프로그램매매: 순매수수량(210) == 매수수량(206)-매도수량(202), 금액(212, 백만원)도 동일 관계
_FIELDS_PROGRAM = {"202": "prm_sell_qty", "206": "prm_buy_qty", "210": "prm_net_qty",
                   "212": "prm_net_amt", "211": "prm_net_amt_irds"}
_RECV_TIMEOUT = 3.0       # recv 대기 상한(초) — stop() 반응성 확보
_RECONNECT_WAIT = (1, 2, 5, 10, 15)  # 재연결 백오프(초)
_MAX_ITEMS = 90           # 키움 실시간 등록 상한(≈97) 대비 안전 여유


def nxt_symbol(stk_cd: str) -> str:
    return f"{stk_cd}_NX"


class KiwoomRealtimeFeed:
    """백그라운드 스레드에서 WS 를 유지하며 최신 체결가를 메모리에 캐시한다.

    스레드 경계: WS 스레드는 **메모리 캐시만** 갱신한다. DB·주문은 전부 호출부(메인 루프)에서
    일어난다 — 통보는 이벤트 플래그로만 넘겨, 재진입·락 문제를 만들지 않는다.
    """

    def __init__(self, symbols: dict[str, bool] | None = None,
                 ttl_sec: float = REALTIME_TTL_SEC, url: str | None = None,
                 subscribe_fills: bool = True,
                 subscribe_supply: bool = SUPPLY_FEED_ENABLED):
        # symbols: {stk_cd: nxt_enabled} — nxt_enabled 면 `_NX` 심볼도 함께 구독
        self._symbols: dict[str, bool] = dict(symbols or {})
        self._ttl = ttl_sec
        self._url = url or (KIWOOM_WS_MOCK_URL if KIWOOM_USE_MOCK else KIWOOM_WS_URL)
        self._subscribe_fills = subscribe_fills
        self._subscribe_supply = subscribe_supply

        self._lock = threading.Lock()
        self._px: dict[tuple[str, str], tuple[int, float]] = {}  # (코드, 보드) → (가격, 수신ts)
        # (코드, 보드) → (수급 필드, 수신ts). 관측 전용이라 가격 캐시와 분리한다 —
        # 여기 값이 낡거나 비어도 손절·스탑 판정은 영향받지 않아야 한다.
        self._supply: dict[tuple[str, str], tuple[dict, float]] = {}
        self._tick_event = threading.Event()
        self._fill_event = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._registered: set[str] = set()   # 현재 세션에 REG 된 item(0B)
        self._registered_supply: set[str] = set()  # 현재 세션에 REG 된 item(0w)
        self._connected = False
        self._ticks = 0
        self._supply_ticks = 0
        self._fills = 0
        self._reconnects = 0
        self._last_error: str | None = None
        self._last_tick_ts = 0.0

    # ── 수명주기 ─────────────────────────────────────────────
    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run_thread, name="kiwoom-ws",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._tick_event.set()  # 대기 중인 호출부를 즉시 깨운다
        t, self._thread = self._thread, None
        if t:
            t.join(timeout=_RECV_TIMEOUT + 2)

    def set_symbols(self, symbols: dict[str, bool]) -> None:
        """구독 종목 갱신. 추가분만 REG 한다(해제는 세션 재연결 시 자연 정리).

        monitor 가동 중엔 종목이 늘지 않지만(매수 없음), 청산 후에도 남은 구독은
        틱만 버려지므로 무해하다 — REMOVE 를 쓰지 않아 로직을 단순하게 유지한다."""
        with self._lock:
            self._symbols = dict(symbols)

    # ── 조회 ────────────────────────────────────────────────
    def get_fresh(self, stk_cd: str, prefer_nxt: bool) -> int | None:
        """TTL 안의 최신 체결가. 없거나 오래됐으면 None(→ 호출부가 REST 폴백).

        prefer_nxt 는 호출부(KiwoomDataClient)의 거래소 판정과 같은 규칙이어야 한다.
        보드가 다르면 가격도 다르므로 **다른 보드로 폴백하지 않는다** — 잘못된 보드의
        가격으로 손절을 판정하는 것이 값이 없는 것보다 위험하다."""
        board = "NXT" if prefer_nxt else "KRX"
        with self._lock:
            hit = self._px.get((stk_cd, board))
        if not hit:
            return None
        price, ts = hit
        if time.time() - ts > self._ttl:
            return None
        return price or None

    def get_supply(self, stk_cd: str, prefer_nxt: bool) -> dict | None:
        """관측용 수급 스냅샷(체결강도·프로그램 순매수) + 수신 나이. 없으면 None.

        ⚠️ **판정에 쓰지 않는다**(2026-08-03 Phase 1 = 수집 전용). 가격과 달리 TTL 로 버리지
        않고 `age_sec` 를 함께 담아 돌려준다 — '언제 온 값인지'까지가 연구 대상이고, 이 값으로
        매도하지 않으므로 stale 이 위험을 만들지 않는다."""
        board = "NXT" if prefer_nxt else "KRX"
        with self._lock:
            hit = self._supply.get((stk_cd, board))
        if not hit:
            return None
        data, ts = hit
        return {**data, "board": board, "age_sec": round(time.time() - ts, 1)}

    def age(self, stk_cd: str, prefer_nxt: bool) -> float | None:
        """해당 보드 최신 틱의 나이(초). 없으면 None."""
        board = "NXT" if prefer_nxt else "KRX"
        with self._lock:
            hit = self._px.get((stk_cd, board))
        return (time.time() - hit[1]) if hit else None

    def wait_for_tick(self, timeout: float) -> bool:
        """새 틱이 오면 즉시 True 로 깨어난다. timeout 초 안에 없으면 False.

        호출부는 이 반환값과 무관하게 판정을 돌려도 된다 — timeout 은 '틱이 없어도
        최소 이 주기로는 점검한다'는 백스톱이다(하한가 등 체결 없는 종목)."""
        got = self._tick_event.wait(timeout)
        self._tick_event.clear()
        return got

    def take_fill_signal(self) -> bool:
        """주문체결통보 수신 여부를 소비(consume)한다. True 면 호출부가 즉시 체결 동기화."""
        if self._fill_event.is_set():
            self._fill_event.clear()
            return True
        return False

    def stats(self) -> dict:
        with self._lock:
            n = len(self._px)
        return {"connected": self._connected, "ticks": self._ticks, "fills": self._fills,
                "supply_ticks": self._supply_ticks,
                "reconnects": self._reconnects, "symbols": n,
                "last_tick_age": round(time.time() - self._last_tick_ts, 1) if self._last_tick_ts else None,
                "error": self._last_error}

    # ── 내부: WS 스레드 ──────────────────────────────────────
    def _items(self) -> list[str]:
        with self._lock:
            syms = dict(self._symbols)
        items: list[str] = []
        for code, nxt in syms.items():
            items.append(code)
            if nxt:
                items.append(nxt_symbol(code))
        if len(items) > _MAX_ITEMS:
            logger.warning("구독 종목 %d개 > 상한 %d — 초과분 제외", len(items), _MAX_ITEMS)
            items = items[:_MAX_ITEMS]
        return items

    def _run_thread(self) -> None:
        """재연결 루프. 어떤 예외도 이 스레드 밖으로 내보내지 않는다(감시 루프 보호)."""
        try:
            import asyncio
            asyncio.run(self._loop())
        except Exception as e:  # pragma: no cover — 방어
            self._last_error = f"스레드 종료: {e}"
            logger.error("실시간 피드 스레드 종료: %s", e)
        finally:
            self._connected = False

    async def _loop(self) -> None:
        import asyncio
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._session()
                attempt = 0
            except Exception as e:
                self._last_error = str(e)
                self._connected = False
                wait = _RECONNECT_WAIT[min(attempt, len(_RECONNECT_WAIT) - 1)]
                attempt += 1
                self._reconnects += 1
                logger.warning("WS 끊김/오류(%s) — %d초 후 재연결", e, wait)
                await asyncio.sleep(wait)

    async def _session(self) -> None:
        import asyncio

        import websockets

        token = (token_repo.get_token() or {}).get("access_token")
        if not token:
            raise RuntimeError("kiwoom 공유 토큰 없음")

        async with websockets.connect(self._url, ping_interval=None, max_size=None) as ws:
            await ws.send(json.dumps({"trnm": "LOGIN", "token": token}))
            self._registered.clear()
            self._registered_supply.clear()

            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=_RECV_TIMEOUT)
                except asyncio.TimeoutError:
                    # 한산한 구간 — 등록이 밀렸으면 이때 보낸다
                    await self._sync_registration(ws)
                    continue
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue

                trnm = msg.get("trnm")
                if trnm == "PING":
                    await ws.send(raw)
                elif trnm == "LOGIN":
                    if str(msg.get("return_code")) != "0":
                        raise RuntimeError(f"LOGIN 실패: {msg.get('return_msg')}")
                    self._connected = True
                    self._last_error = None
                    logger.info("실시간 피드 접속: %s", self._url)
                    await self._sync_registration(ws, fills=True)
                elif trnm == "REG":
                    if str(msg.get("return_code")) != "0":
                        logger.warning("REG 거부: %s", msg.get("return_msg"))
                elif trnm == "REAL":
                    self._on_real(msg)

    async def _sync_registration(self, ws, fills: bool = False) -> None:
        """아직 REG 안 된 심볼을 등록한다(추가분만). 로그인 직후엔 체결통보도 함께."""
        if not self._connected:
            return
        if fills and self._subscribe_fills:
            await ws.send(json.dumps({
                "trnm": "REG", "grp_no": "2", "refresh": "1",
                "data": [{"item": [""], "type": [_TYPE_FILL]}]}))
        items = self._items()
        pending = [i for i in items if i not in self._registered]
        if pending:
            await ws.send(json.dumps({
                "trnm": "REG", "grp_no": "1", "refresh": "1",
                "data": [{"item": pending, "type": [_TYPE_TRADE]}]}))
            self._registered.update(pending)
            logger.info("실시간 구독 등록 %d종목: %s", len(pending), ",".join(pending))
        # 수급 관측(0w)은 **별도 그룹**으로 등록한다 — 거부돼도 시세(0B) 구독이 흔들리지 않게.
        if not self._subscribe_supply:
            return
        pending_supply = [i for i in items if i not in self._registered_supply]
        if pending_supply:
            await ws.send(json.dumps({
                "trnm": "REG", "grp_no": "3", "refresh": "1",
                "data": [{"item": pending_supply, "type": [_TYPE_PROGRAM]}]}))
            self._registered_supply.update(pending_supply)
            logger.info("수급 관측 구독 등록 %d종목(0w)", len(pending_supply))

    def _on_real(self, msg: dict) -> None:
        now = time.time()
        got_tick = False
        for d in msg.get("data") or []:
            dtype = d.get("type")
            if dtype == _TYPE_FILL:
                self._fills += 1
                self._fill_event.set()
                continue
            item = str(d.get("item") or "")
            values = d.get("values") or {}
            if not item:
                continue
            code = item[:-3] if item.endswith("_NX") else item
            board = str(values.get("9081") or ("NXT" if item.endswith("_NX") else "KRX")).upper()
            if dtype == _TYPE_PROGRAM:
                # 프로그램매매(수급 관측) — 가격 캐시·틱 이벤트는 건드리지 않는다.
                # 이 타입으로 손절이 판정되거나 대기가 깨지면 안 된다(관측 전용).
                self._merge_supply(code, board, values, _FIELDS_PROGRAM, now)
                self._supply_ticks += 1
                continue
            if dtype != _TYPE_TRADE:
                continue
            price = abs(to_int(values.get("10")))
            if price <= 0:
                continue
            with self._lock:
                self._px[(code, board)] = (price, now)
            if self._subscribe_supply:
                self._merge_supply(code, board, values, _FIELDS_TRADE, now)
            self._ticks += 1
            self._last_tick_ts = now
            got_tick = True
        if got_tick:
            self._tick_event.set()

    def _merge_supply(self, code: str, board: str, values: dict,
                      fields: dict[str, str], now: float) -> None:
        """수급 필드를 (코드, 보드) 슬롯에 병합한다(0B 체결 + 0w 프로그램이 한 스냅샷을 이룬다).

        누락 필드는 기존 값을 유지한다 — 0B 와 0w 는 갱신 주기가 달라 매 틱이 반쪽짜리다."""
        picked = {name: values[fid] for fid, name in fields.items() if fid in values}
        if not picked:
            return
        with self._lock:
            prev = self._supply.get((code, board))
            merged = dict(prev[0]) if prev else {}
            merged.update(picked)
            self._supply[(code, board)] = (merged, now)
