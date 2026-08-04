"""모니터 탭 실시간 시세 스트림 — 대시보드 SSE(`GET /monitor/stream`) 전용 시세 공급자.

매도 워커(`workers/monitor.py`)는 이미 키움 WS 틱으로 손절을 판정하지만, 그 피드는 워커
**프로세스 안**에 있어 대시보드(API :8002)가 볼 수 없다. 그래서 모니터 탭은 15초 폴링으로
`/monitor` 를 다시 부르고, 그때마다 종목당 REST 2콜(ka10001+ka10081)을 쓰고 있었다.
이 모듈은 같은 `KiwoomRealtimeFeed` 를 **API 프로세스에서도** 띄워, 캐시에서 시세를 꺼내
1초 간격으로 밀어 준다(구독 후 REST 0콜 — 새 부하가 아니라 교체다).

설계 결정 세 가지:

1. **보는 사람이 있을 때만 WS 를 붙인다**(refcount). 같은 키움 토큰으로 워커와 세션이
   동시에 살아 있을 때 양쪽이 다 틱을 받는지는 아직 미검증이다
   (`docs/plan/realtime-ws-migration.md` §2.1 — 세션 2개가 거부되지 않는 것만 확인).
   만약 뒤 세션만 틱을 받으면 **매도 워커의 판정이 15초 REST 로 후퇴**한다(fail-safe 이지만
   손해). 그래서 겹치는 시간을 '내가 모니터 탭을 보는 동안'으로 한정하고, 마지막 구독자가
   떠나면 `PRICE_STREAM_IDLE_SEC` 뒤에 세션을 닫는다. 간섭 여부는 워커 하트비트
   (`monitor_poll.ws.ticks`/`reconnects`)로 확인한다 — 이상하면 `PRICE_STREAM_ENABLED=0`.
2. **시세 조립은 프로듀서 스레드 하나만 한다.** SSE 제너레이터는 완성된 스냅샷만 읽으므로
   탭이 몇 개 열려도 DB·REST 비용이 늘지 않고, API 이벤트 루프에서 블로킹 호출이 없다.
3. **가격 판정 규칙은 `get_display_price` 와 동일**(정규장=KRX 보드 / 그 밖=NXT 가능 종목만
   NXT). 틱이 없거나 TTL 초과면 REST 로 폴백하되, 폴백은 종목당
   `PRICE_STREAM_REST_TTL_SEC` 간격으로만 한다(1초 푸시가 REST 를 초당 두드리지 않게).

⚠️ 이 모듈은 **표시 전용**이다. 주문·손절 판정은 전혀 경유하지 않으며, 죽어도 대시보드가
15초 폴링(`/monitor`)으로 종전대로 돌아간다.
"""
import logging
import threading
import time

from core.config import (
    PRICE_STREAM_ENABLED,
    PRICE_STREAM_IDLE_SEC,
    PRICE_STREAM_PUSH_SEC,
    PRICE_STREAM_REST_TTL_SEC,
)
from core.kiwoom_data_client import KiwoomDataClient, _in_krx_session
from core.repository import position as position_repo

logger = logging.getLogger("PriceStream")

_POS_REFRESH_SEC = 5.0   # 보유 종목 목록 재조회 주기(초) — 가격보다 훨씬 덜 바뀐다


def _default_feed_factory(symbols: dict[str, bool]):
    """모니터 탭용 피드 — **시세(0B)만** 구독한다.

    체결통보(00)·수급 관측(0w)은 워커의 몫이다. 표시 목적으로 계정 단위 통보까지 구독하면
    같은 이벤트를 두 세션이 받게 되고, 이 모듈이 관여할 이유가 없는 축이다."""
    from core.realtime_feed import KiwoomRealtimeFeed

    feed = KiwoomRealtimeFeed(symbols=symbols, subscribe_fills=False,
                             subscribe_supply=False)
    feed.start()
    return feed


class PriceStream:
    """구독자가 있을 때만 살아 있는 시세 스냅샷 공급자.

    수명주기: `acquire()` → (없으면 피드+프로듀서 스레드 기동) … `release()` →
    구독자 0 이 `PRICE_STREAM_IDLE_SEC` 지속되면 프로듀서가 스스로 피드를 닫고 종료한다.
    """

    def __init__(self, feed_factory=_default_feed_factory,
                 data_client_factory=KiwoomDataClient,
                 enabled: bool = PRICE_STREAM_ENABLED,
                 push_sec: float = PRICE_STREAM_PUSH_SEC,
                 idle_sec: float = PRICE_STREAM_IDLE_SEC,
                 rest_ttl_sec: float = PRICE_STREAM_REST_TTL_SEC):
        self.enabled = enabled
        self._feed_factory = feed_factory
        self._data_factory = data_client_factory
        self._push = max(push_sec, 0.2)
        self._idle = idle_sec
        self._rest_ttl = rest_ttl_sec

        self._lock = threading.Lock()
        self._subs = 0
        self._thread: threading.Thread | None = None
        self._feed = None
        self._snapshot: dict = {"seq": 0, "prices": {}, "ws": None}
        self._nxt: dict[str, bool] = {}                     # 종목 → NXT 가능(REST 1회 후 캐시)
        self._rest: dict[str, tuple[int, bool, float]] = {}  # 종목 → (가격, is_nxt, 조회ts)
        self._idle_since: float | None = None

    # ── 구독자 수명주기 ──────────────────────────────────────
    def acquire(self) -> bool:
        """구독자 1명 등록. 피드가 꺼져 있으면 켠다. 비활성 설정이면 False."""
        if not self.enabled:
            return False
        with self._lock:
            self._subs += 1
            self._idle_since = None
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="price-stream",
                                                daemon=True)
                self._thread.start()
        return True

    def release(self) -> None:
        with self._lock:
            self._subs = max(0, self._subs - 1)
            if self._subs == 0:
                self._idle_since = time.time()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot

    def fresh_prices(self, max_age: float = 5.0) -> dict:
        """스냅샷이 신선할 때만 가격을 돌려준다(스트림이 멈춘 뒤 남은 stale 값을 쓰지 않게).

        `/monitor` 15초 폴링이 이걸 먼저 보고 REST 조회를 생략한다 — 스트림이 살아 있는 동안
        폴링 응답과 SSE 가 **같은 값**을 쓰게 되어 두 경로 사이 가격이 튀지 않는다."""
        with self._lock:
            snap = self._snapshot
        at = snap.get("at")
        if not at or time.time() - at > max_age:
            return {}
        return snap.get("prices") or {}

    def stats(self) -> dict:
        with self._lock:
            feed = self._feed
            subs = self._subs
        return {"subscribers": subs, "ws": feed.stats() if feed else None}

    # ── 프로듀서 스레드 ──────────────────────────────────────
    def _run(self) -> None:
        """스냅샷 갱신 루프. 어떤 예외도 밖으로 내보내지 않는다(API 프로세스 보호)."""
        data = self._data_factory()
        feed = None
        seq = 0
        positions: list[dict] = []
        pos_ts = 0.0
        try:
            while True:
                if self._should_stop():
                    break
                now = time.time()
                if now - pos_ts >= _POS_REFRESH_SEC or not positions:
                    positions = self._open_positions()
                    pos_ts = now
                    feed = self._ensure_feed(feed, positions)
                seq += 1
                prices = self._build_prices(data, feed, positions)
                with self._lock:
                    self._snapshot = {
                        "seq": seq,
                        "at": now,
                        "ts": time.strftime("%H:%M:%S"),
                        "prices": prices,
                        "ws": feed.stats() if feed else None,
                    }
                time.sleep(self._push)
        except Exception as e:  # pragma: no cover — 방어
            logger.error("시세 스트림 프로듀서 종료: %s", e)
        finally:
            with self._lock:
                self._feed = None
            if feed is not None:
                try:
                    feed.stop()
                    logger.info("모니터 시세 피드 종료: %s", feed.stats())
                except Exception as e:
                    logger.warning("시세 피드 종료 실패: %s", e)

    def _should_stop(self) -> bool:
        """구독자 0 이 idle 만큼 지속되면 종료. 종료 판단·해제를 같은 락에서 해
        `acquire()` 와 경쟁하지 않는다(락 안에서 구독자 수를 다시 확인)."""
        with self._lock:
            if self._subs > 0 or self._idle_since is None:
                return False
            if time.time() - self._idle_since < self._idle:
                return False
            self._thread = None
            return True

    def _open_positions(self) -> list[dict]:
        try:
            return position_repo.get_open_positions() or []
        except Exception as e:
            logger.warning("보유 포지션 조회 실패 — 이전 목록 유지: %s", e)
            return []

    def _ensure_feed(self, feed, positions: list[dict]):
        """보유 종목이 있으면 피드를 띄우고, 새 종목이 생기면 구독을 추가한다."""
        codes = [p["stk_cd"] for p in positions]
        if not codes:
            return feed
        symbols = {c: self._nxt_enabled(c) for c in codes}
        if feed is None:
            try:
                feed = self._feed_factory(symbols)
            except Exception as e:
                logger.warning("시세 피드 기동 실패 — REST 폴백으로 계속: %s", e)
                return None
            with self._lock:
                self._feed = feed
            logger.info("모니터 시세 피드 기동 %d종목", len(symbols))
            return feed
        try:
            if set(symbols) - set(feed._symbols):  # noqa: SLF001 — 같은 도메인 내부 상태
                feed.set_symbols({**feed._symbols, **symbols})  # noqa: SLF001
        except Exception as e:
            logger.warning("시세 피드 구독 갱신 실패: %s", e)
        return feed

    def _nxt_enabled(self, stk_cd: str) -> bool:
        if stk_cd not in self._nxt:
            try:
                self._nxt[stk_cd] = self._data_factory().is_nxt_enabled(stk_cd)
            except Exception as e:
                logger.warning("NXT 여부 조회 실패 [%s]: %s", stk_cd, e)
                return False
        return self._nxt[stk_cd]

    def _build_prices(self, data, feed, positions: list[dict]) -> dict:
        """종목별 표시 가격 스냅샷. WS 캐시 우선, 없으면 REST(종목당 TTL 간격) 폴백."""
        krx = _in_krx_session()
        out: dict[str, dict] = {}
        for p in positions:
            code = p["stk_cd"]
            prefer_nxt = (not krx) and self._nxt_enabled(code)
            cached = None
            if feed is not None:
                try:
                    cached = feed.get_fresh(code, prefer_nxt=prefer_nxt)
                except Exception as e:
                    logger.warning("시세 캐시 조회 실패 [%s]: %s", code, e)
            if cached:
                age = None
                try:
                    age = feed.age(code, prefer_nxt=prefer_nxt)
                except Exception:
                    pass
                out[code] = {"prc": cached, "is_nxt": prefer_nxt, "src": "ws", "age": age}
                continue
            rest = self._rest_price(data, code)
            if rest:
                prc, is_nxt, ts = rest
                out[code] = {"prc": prc, "is_nxt": is_nxt, "src": "rest",
                             "age": round(time.time() - ts, 1)}
        return out

    def _rest_price(self, data, stk_cd: str):
        hit = self._rest.get(stk_cd)
        if hit and time.time() - hit[2] < self._rest_ttl:
            return hit
        try:
            prc, is_nxt = data.get_display_price(stk_cd)
        except Exception as e:
            logger.warning("REST 시세 폴백 실패 [%s]: %s", stk_cd, e)
            return hit  # 직전 값이라도 유지(표시 전용 — 없는 것보다 낫다)
        if not prc:
            return hit
        hit = (prc, is_nxt, time.time())
        self._rest[stk_cd] = hit
        return hit


_stream: PriceStream | None = None


def get_price_stream() -> PriceStream:
    """프로세스 단일 인스턴스(모든 SSE 구독자가 한 피드를 공유한다)."""
    global _stream
    if _stream is None:
        _stream = PriceStream()
    return _stream
