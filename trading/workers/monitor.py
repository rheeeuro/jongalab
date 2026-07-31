"""시초가 청산 윈도우 트레일링 스탑 + 하드 손절 감시 워커.

판정 주기를 **동작 성격별로 분리**한다(2026-07-31 WS 전환). 손절 판정은 지연이 곧 손실이라
틱 즉시로 올리고, 주문 전송·트레일링 상향·유지보수는 기존 15초 주기를 유지한다:

| 동작 | 주기 | 근거 |
|---|---|---|
| 뉴스베토·하드손절·스탑 breach **판정** | WS 틱 즉시(백스톱 1초) | 15초 폴링은 노이즈 필터가 아니라 무작위 샘플링 — 진짜 하락이면 손절선보다 낮게 팔리고, 순간 급락이면 운에 맡긴다 |
| 매도 주문 **전송·재시도** | 종목별 15초 쿨다운 | 2026-07-10 HLB 하한가 때 15초 주기로도 거부 238건. 판정 주기를 주문에 물리면 유량 제한에 걸려 하한가 풀림을 놓친다 |
| 트레일링 스탑 **상향** | 15초(기존) | TRAIL_PCT=0.75 가 15초 주기 백테스트로 튜닝된 값이다. 상향을 촘촘히 하면 실효 TRAIL_PCT 가 좁아져(비채택된 0.5 쪽으로) 파라미터가 무단 변경된다 |
| 유지보수(체결동기화·미체결정리) | 15초(기존) | 지연 무해. 단 체결통보(WS 00) 수신 시엔 즉시 동기화 |

판정 내용은 종전과 동일하다(순서도 동일):
  0) 뉴스 베토: jongalab news_guard 가 밤사이 중대 악재로 판정한 종목(severe=1)은
     **가격 무관 즉시 전량 매도**. 조회 실패 시 미개입(core/news_veto.py).
  1) 하드 손절(칼손절): 현재가가 평단 대비 HARD_STOP_LOSS_PCT% 아래면 즉시 전량 매도.
  2) 스탑/저가이탈: settle_plan 의 stop_price 이하면 즉시 잔량 전량 매도.
  3) 트레일링 스탑: 위 둘 미발동이면 stop_price 를 고점 추종으로 상향(단조 증가).

⚠️ 실시간 피드는 **항상 옵셔널**이다. 연결 실패·틱 없음·TTL 초과면 `check_once`(15초 REST
경로)가 그대로 판정하므로, WS 가 죽어도 현행 동작과 동일하게 감시가 유지된다.

가동 구간은 평일 08:00~09:30 (NXT 개장 직후 ~ KRX 데드라인 + 여유)으로 한정한다.
08:00·09:00 정각 1분은 시가 단일가 체결 전 stale 가격 오발동 위험이 있어 평가를 스킵한다.
settle KRX 단계(09:28)가 데드라인으로 미체결 잔량을 강제 청산한다.

pm2 cron 워커(autorestart:false, cron_restart '1 8 * * 1-5'): 08:01 에 기동돼 가동 구간이
끝나면 스스로 종료하고, 다음 평일 아침 cron 으로 재기동된다. 키움 스톱주문 대신 감시로 근사한다.
"""
import time
import logging
from datetime import datetime

import requests

from core.config import (
    HARD_STOP_LOSS_PCT,
    TRAIL_PCT,
    US_STOP_TIGHTEN_ENABLED,
    US_STOP_TIGHTEN_MAX,
    US_STOP_MIN_PCT,
    FUTURES_FLAT_BAND,
    FUTURES_FULL_CUT_PCT,
    JONGALAB_BASE_URL,
    REALTIME_FEED_ENABLED,
    MONITOR_TICK_WAIT_SEC,
    SELL_RETRY_COOLDOWN_SEC,
)
from core.logging_setup import setup_logging
from core.execution_engine import ExecutionEngine
from core.fill_sync import sync_fills
from core.order_maintenance import cancel_stale_orders, reconcile_dead_sent
from core import news_veto
# 거래소 판정 규칙의 단일 소스 — 틱 조회 시 어느 보드(KRX/NXT) 가격을 볼지 결정한다.
# 규칙을 여기 복제하면 데이터 클라이언트와 어긋날 수 있어 그대로 재사용한다.
from core.kiwoom_data_client import _in_krx_session
from core.notifications import notify_admin
from core.repository import position as position_repo
from core.repository import settle_plan as plan_repo
from core.repository import audit_log

setup_logging()
logger = logging.getLogger("Monitor")

POLL_SEC = 15  # 유지보수·트레일링 상향·하트비트 주기(기존 유지)


def _beat(payload: dict) -> None:
    """폴링 하트비트 — 대시보드 '모니터' 탭이 워커 가동 여부를 판별하는 신호.
    기록 실패가 감시 루프를 막지 않도록 예외를 삼킨다(순수 로깅)."""
    try:
        audit_log.append("monitor_poll", None, payload)
    except Exception as e:
        logger.warning("하트비트 기록 실패: %s", e)


# ── 오버나잇 US 결과로 하드손절 강화 (KRX 보유분 대비책) ──
# KRX 종가베팅 보유분은 매수(15:20) 시점 미국장이 다크라 futures_gate 의 US 확장 축을 못 받는다.
# 대신 여기(08:01~) 시점엔 지난밤 미국 정규장이 이미 마감 → 그 결과(regular_ret)로 오버나잇
# 리스크를 읽어, 급락 밤이었으면 그날 하드손절 폭을 더 좁게(보수적) 조인다. 축소 전용.
_us_tighten_cache = {"computed": False, "pct": None}


def _min_opt(*vals):
    """None 무시 최소값(둘 다 None 이면 None) — 여러 프록시 중 가장 약세를 택해 보수적으로."""
    present = [v for v in vals if v is not None]
    return min(present) if present else None


def _overnight_intensity(regular_ret) -> float:
    """지난밤 US 정규장 하락 강도 0~1 (futures_gate 와 동일 램프: -FLAT_BAND=0 ~ -FULL_CUT_PCT=1)."""
    if regular_ret is None or regular_ret >= -FUTURES_FLAT_BAND:
        return 0.0
    span = FUTURES_FULL_CUT_PCT - FUTURES_FLAT_BAND
    if span <= 0:
        return 1.0
    return min(1.0, (-regular_ret - FUTURES_FLAT_BAND) / span)


def effective_hard_stop_pct() -> float:
    """오버나잇 US 정규장(반도체 min(SOXX,SKHY) + 한국 min(EWY,KORU/3)) 결과로 강화된 하드손절 %.

    급락 밤일수록 손절을 좁게 — HARD_STOP_LOSS_PCT 에서 최대 US_STOP_TIGHTEN_MAX %p 줄이되
    US_STOP_MIN_PCT 밑으론 안 내린다(축소 전용). 프로세스당 1회 계산·캐시(오버나잇 결과는 아침 내내 고정).
    비활성/취득 실패면 기본 HARD_STOP_LOSS_PCT(미개입)."""
    if not US_STOP_TIGHTEN_ENABLED:
        return HARD_STOP_LOSS_PCT
    if _us_tighten_cache["computed"]:
        return _us_tighten_cache["pct"]
    pct = HARD_STOP_LOSS_PCT
    try:
        resp = requests.get(f"{JONGALAB_BASE_URL}/api/us-extended", timeout=5)
        resp.raise_for_status()
        data = resp.json() or {}

        def _reg(sym):
            v = (data.get(sym) or {}).get("regular_ret")
            return float(v) if v is not None else None

        koru = _reg("KORU")
        semis = _min_opt(_reg("SOXX"), _reg("SKHY"))
        korea = _min_opt(_reg("EWY"), koru / 3.0 if koru is not None else None)
        intensity = max(_overnight_intensity(semis), _overnight_intensity(korea))
        pct = max(US_STOP_MIN_PCT, round(HARD_STOP_LOSS_PCT - US_STOP_TIGHTEN_MAX * intensity, 2))
        if intensity > 0:
            logger.info("오버나잇 US 하락(강도 %.2f) → 하드손절 %.1f%%→%.1f%% 강화 (반도체 %s / 한국 %s)",
                        intensity, HARD_STOP_LOSS_PCT, pct, semis, korea)
            audit_log.append("monitor_us_tighten", None, {
                "intensity": round(intensity, 3), "base_pct": HARD_STOP_LOSS_PCT,
                "eff_pct": pct, "semis_reg": semis, "korea_reg": korea})
    except Exception as e:
        logger.warning("오버나잇 US 조회 실패 — 하드손절 기본값 유지: %s", e)
        pct = HARD_STOP_LOSS_PCT
    _us_tighten_cache.update(computed=True, pct=pct)
    return pct


def in_window(now: datetime) -> bool:
    """모니터 가동 구간: 평일 08:00~09:30 (NXT 개장 ~ KRX 잔량청산 + 여유).

    08:00·09:00 개장 직후 1분은 시가 체결 전 stale 가격 오발동 위험이 있어
    in_open_warmup() 으로 평가를 스킵한다(가동 자체는 08:00부터)."""
    if now.weekday() >= 5:
        return False
    return (8, 0) <= (now.hour, now.minute) <= (9, 30)


def resolve_sell_venue(engine: ExecutionEngine, stk_cd: str, now: datetime) -> str | None:
    """매도 거래소 결정. None 이면 지금은 이 종목을 매도할 수 없음(보류).

      - KRX 정규장(09:00~15:30): 항상 KRX(시장가).
      - 그 외(개장 전 NXT 시간대): NXT 거래 가능 종목만 NXT(최유리IOC).
        NXT 불가 종목은 NXT 주문이 키움에서 **거부**되고(비-NXT 종목의 NXT 명시 거부),
        KRX 는 아직 개장 전이라 매도할 곳이 없다 → None(09:00 KRX 개장까지 보류).

    is_nxt_enabled 는 매도 발동 시점에만 조회한다(폴링마다 X). 조회 실패 시 False(보수적)라
    잠깐 보류될 수 있으나, 다음 판정에서 재조회되어 자가 복구된다."""
    hm = (now.hour, now.minute)
    if (9, 0) <= hm < (15, 30):
        return "KRX"
    return "NXT" if engine.data.is_nxt_enabled(stk_cd) else None


def in_open_warmup(now: datetime) -> bool:
    """거래소 개장 직후 1분(NXT 08:00~08:01, KRX 09:00~09:01)은 평가를 스킵한다.

    시가 단일가 체결이 ka10001 `cur_prc`에 반영되기 전이라, 이 구간엔 cur_prc 가
    실시간가가 아니라 기준가(=전일 종가)를 돌려줄 수 있다. 그 stale 값으로 스탑/손절을
    판정하면 실제 시장이 스탑 위에 있어도 오발동해 잔량을 강제 청산한다(반대로 진짜
    갭하락 날엔 갭 바닥에 시장가로 던질 위험). 시가가 체결돼 가격이 안정되는 1분간 대기.

    WS 틱 판정에도 동일 적용한다 — 시가 단일가 전 얇은 호가의 단발 체결로 칼손절이
    오발동하는 위험은 가격 출처가 REST 든 WS 든 같다."""
    hm = (now.hour, now.minute)
    return hm == (8, 0) or hm == (9, 0)


def _exit_confirmed(stk_cd: str) -> bool:
    """매도 후 포지션이 실제로 청산됐는지(체결 확인). paper 는 즉시 반영돼 True,
    live 는 체결 동기화가 반영된 뒤 True 가 된다.

    '전송됨(sent)'만으로 plan 을 해제하면, 최유리IOC 가 접수돼도 0주 체결로 소멸했을 때
    감시가 풀려 포지션이 고아가 된다. 실제 청산이 확인될 때만 감시를 해제하기 위한 게이트."""
    p = position_repo.get_position(stk_cd)
    return not p or p["qty"] < 1


class MonitorState:
    """틱 판정이 참조하는 스냅샷 + 종목별 매도 쿨다운.

    틱마다 DB 를 읽으면(삼성전자 단독 32틱/초) DB 가 감당하지 못한다. 포지션·플랜·베토는
    15초 주기(`check_once`)에만 읽어 메모리에 두고, 틱 판정은 이 스냅샷 + WS 가격으로
    **순수 계산**만 한다. 실제 매도 발동 시점엔 `_exit_confirmed`/`execute_sell` 이
    DB·브로커를 다시 보므로, 스냅샷이 한 주기 오래됐어도 과매도로 이어지지 않는다.
    """

    def __init__(self):
        self.positions: dict = {}
        self.plans: dict = {}
        self.vetoes: dict = {}
        self.last_sell: dict[str, float] = {}  # 종목 → 마지막 매도 '전송 시도' ts(쿨다운 기준)
        self.last_slow_ts: float = 0.0         # 직전 15초 판정 시각(틱 이득 사후 채점용)
        self.cooldown_skips: int = 0           # 쿨다운으로 억제한 재전송 횟수(하트비트 노출)

    def refresh(self) -> None:
        """15초 주기 스냅샷 갱신. 베토 조회는 실패/비활성 시 {} — 감시 루프는 계속 돈다."""
        self.plans = {p["stk_cd"]: p for p in plan_repo.get_active_plans()}
        self.positions = {p["stk_cd"]: p for p in position_repo.get_open_positions()}
        self.vetoes = news_veto.get_severe_verdicts()

    def forget(self, stk_cd: str) -> None:
        """청산 확인된 종목을 스냅샷에서 제거 — 다음 갱신까지 헛 판정하지 않게."""
        self.positions.pop(stk_cd, None)
        self.plans.pop(stk_cd, None)

    def sell_allowed(self, stk_cd: str) -> bool:
        """종목별 매도 전송 쿨다운. 첫 전송은 항상 허용, 이후 SELL_RETRY_COOLDOWN_SEC 간격."""
        last = self.last_sell.get(stk_cd, 0.0)
        if time.time() - last >= SELL_RETRY_COOLDOWN_SEC:
            return True
        self.cooldown_skips += 1
        return False

    def mark_sell(self, stk_cd: str) -> None:
        """전송 성공/거부와 무관하게 시도 시각을 남긴다 — 거부도 주문 전송이라 유량을 쓴다."""
        self.last_sell[stk_cd] = time.time()


def _lag_payload(state: MonitorState, path: str) -> dict:
    """감사 payload 공통 진단: 어느 경로로 발동했고, 15초 폴링이었다면 얼마나 늦었을지.

    `slow_wait_ms` = 다음 15초 판정까지 남은 시간 = 종전 설계가 더 기다렸을 지연.
    이 값을 쌓아두면 '즉시 판정이 실제로 이득이었나'를 사후에 채점할 수 있다(비용 0)."""
    out = {"path": path}
    if path == "tick" and state.last_slow_ts:
        elapsed = time.time() - state.last_slow_ts
        out["slow_wait_ms"] = max(0, round((POLL_SEC - elapsed) * 1000))
    return out


def _evaluate_position(engine: ExecutionEngine, state: MonitorState, stk_cd: str,
                       pos: dict, cur: int, hard_pct: float, now: datetime,
                       allow_trail: bool, path: str) -> None:
    """한 종목 판정·발동. 순서(베토→하드손절→스탑→트레일링)와 내용은 종전과 동일하다.

    allow_trail=False(틱 경로)면 트레일링 상향만 건너뛴다 — 상향은 TRAIL_PCT 가 튜닝된
    15초 주기를 유지해야 실효 파라미터가 바뀌지 않는다(스탑 breach 감지는 즉시).
    """
    plan = state.plans.get(stk_cd)
    trade_date = plan["trade_date"] if plan else now.strftime("%Y%m%d")
    diag = _lag_payload(state, path)

    # 0) 뉴스 베토: 밤사이 중대 악재 판정(jongalab news_guard) 종목은 가격 무관 즉시 전량매도.
    #    하드손절보다 앞 — 갭이 아직 가격에 반영되기 전에도(악재 확인 즉시) 탈출한다.
    veto = state.vetoes.get(stk_cd)
    if veto:
        if not state.sell_allowed(stk_cd):
            return
        venue = resolve_sell_venue(engine, stk_cd, now)
        if venue is None:
            logger.info("뉴스베토 발동이나 매도 보류 [%s] — NXT 불가, 09:00 KRX 개장 후 청산", stk_cd)
            return
        state.mark_sell(stk_cd)
        sold = engine.execute_sell(trade_date, stk_cd, pos["qty"], cur,
                                   dmst_stex_tp=venue, tag="newsveto")
        audit_log.append("monitor_newsveto", stk_cd, {
            "cur": cur, "qty": pos["qty"], "venue": venue,
            "category": veto.get("category"), "confidence": veto.get("confidence"),
            "reason": veto.get("reason"), "sent": bool(sold), **diag})
        if sold:
            notify_admin(
                f"🚨 *뉴스 베토 전량매도* {veto.get('stk_nm') or stk_cd}(`{stk_cd}`) "
                f"{pos['qty']}주 @{cur:,} ({venue})\n"
                f"분류: {veto.get('category')} · 확신도 {veto.get('confidence')}\n"
                f"사유: {veto.get('reason')}")
            if _exit_confirmed(stk_cd):
                if plan:
                    plan_repo.deactivate(plan["trade_date"], stk_cd,
                                         f"뉴스베토 전량매도 @{cur}")
                state.forget(stk_cd)
                logger.info("뉴스베토 청산완료 [%s] %d주 @%d (%s, %s)",
                            stk_cd, pos["qty"], cur, venue, veto.get("category"))
            else:
                logger.info("뉴스베토 매도 전송 [%s] @%d — 체결 미확인, 다음 판정에서 재확인/재시도",
                            stk_cd, cur)
        else:
            logger.warning("뉴스베토 매도 거부/미전송(또는 멱등 스킵) [%s] @%d — 쿨다운 후 재시도",
                           stk_cd, cur)
        return

    # 1) 하드 손절(칼손절): 평단 대비 -hard_pct% 이하면 plan 유무 무관 전량매도
    #    hard_pct 는 오버나잇 US 급락 밤이면 기본(HARD_STOP_LOSS_PCT)보다 좁혀진 값.
    hard_stop = round(pos["avg_price"] * (1 - hard_pct / 100))
    if cur <= hard_stop:
        if not state.sell_allowed(stk_cd):
            return
        venue = resolve_sell_venue(engine, stk_cd, now)
        if venue is None:
            # NXT 불가 종목 + KRX 개장 전: 매도할 곳이 없어 보류(NXT 주문은 거부됨).
            # 09:00 KRX 개장 후 판정에서 KRX 시장가로 청산된다.
            logger.info("하드손절 발동이나 매도 보류 [%s] @%d (선 %d) — NXT 불가, 09:00 KRX 개장 후 청산",
                        stk_cd, cur, hard_stop)
            return
        state.mark_sell(stk_cd)
        sold = engine.execute_sell(trade_date, stk_cd, pos["qty"], cur,
                                   dmst_stex_tp=venue, tag="hardstop")
        audit_log.append("monitor_hardstop", stk_cd, {
            "cur": cur, "hard_stop": hard_stop, "avg_price": pos["avg_price"],
            "qty": pos["qty"], "pct": hard_pct, "sent": bool(sold), **diag})
        if sold and _exit_confirmed(stk_cd):
            if plan:
                plan_repo.deactivate(plan["trade_date"], stk_cd,
                                     f"하드손절 청산완료 @{cur}(<= {hard_stop}, 평단 {pos['avg_price']})")
            state.forget(stk_cd)
            logger.info("하드손절 청산완료 [%s] %d주 @%d (선 %d, 평단 %d, -%.1f%%)",
                        stk_cd, pos["qty"], cur, hard_stop, pos["avg_price"], hard_pct)
        elif sold:
            logger.info("하드손절 매도 전송 [%s] @%d — 체결 미확인, 다음 판정에서 재확인/재시도",
                        stk_cd, cur)
        else:
            logger.warning("하드손절 매도 거부/미전송 [%s] @%d (선 %d) — plan 유지, 쿨다운 후 재시도",
                           stk_cd, cur, hard_stop)
        return

    # 2) 스탑/저가이탈: settle_plan 의 stop_price 이하면 잔량 전량매도
    if plan and cur <= plan["stop_price"]:
        if not state.sell_allowed(stk_cd):
            return
        venue = resolve_sell_venue(engine, stk_cd, now)
        if venue is None:
            logger.info("스탑 발동이나 매도 보류 [%s] @%d (선 %d) — NXT 불가, 09:00 KRX 개장 후 청산",
                        stk_cd, cur, plan["stop_price"])
            return
        state.mark_sell(stk_cd)
        sold = engine.execute_sell(plan["trade_date"], stk_cd, pos["qty"], cur,
                                   dmst_stex_tp=venue, tag="stop")
        audit_log.append("monitor_stop", stk_cd, {
            "cur": cur, "stop": plan["stop_price"], "qty": pos["qty"],
            "sent": bool(sold), **diag})
        if sold and _exit_confirmed(stk_cd):
            plan_repo.deactivate(plan["trade_date"], stk_cd,
                                 f"스탑/저가이탈 청산완료 @{cur}(<= {plan['stop_price']})")
            state.forget(stk_cd)
            logger.info("스탑 청산완료 [%s] %d주 @%d (선 %d)",
                        stk_cd, pos["qty"], cur, plan["stop_price"])
        elif sold:
            logger.info("스탑 매도 전송 [%s] @%d — 체결 미확인, plan 유지(다음 판정 재확인/재시도)",
                        stk_cd, cur)
        else:
            logger.warning("스탑 매도 거부/미전송 [%s] @%d (선 %d) — plan 유지, 쿨다운 후 재시도",
                           stk_cd, cur, plan["stop_price"])
        return

    # 3) 트레일링 스탑: 매도 미발동(잔량 보유 지속) 시 고점 추종으로 스탑선 상향.
    #    cur > stop_price 가 보장되는 분기라 같은 판정 내 재발동 없음(새 스탑 = cur*(1-pct) < cur).
    #    상향은 15초 주기 전용(allow_trail) — TRAIL_PCT 튜닝 전제를 보존한다.
    if allow_trail and plan:
        trail_stop = round(cur * (1 - TRAIL_PCT / 100))
        if trail_stop > plan["stop_price"] and plan_repo.raise_stop(
                plan["trade_date"], stk_cd, trail_stop, note=f"trail @{cur}"):
            logger.info("트레일링 [%s] 스탑 상향 %d→%d (현재가 %d, -%.1f%%)",
                        stk_cd, plan["stop_price"], trail_stop, cur, TRAIL_PCT)
            audit_log.append("monitor_trail", stk_cd, {
                "old": plan["stop_price"], "new": trail_stop, "cur": cur, "pct": TRAIL_PCT})
            plan["stop_price"] = trail_stop  # 스냅샷도 갱신 — 틱 경로가 새 스탑선으로 판정


def check_once(engine: ExecutionEngine, state: MonitorState | None = None) -> None:
    """15초 주기 판정 — 유지보수 + 스냅샷 갱신 + 전 종목 판정(트레일링 상향 포함).

    실시간 피드가 없거나 죽었을 때 **이 경로만으로 종전과 동일하게** 감시가 돌아간다
    (가격도 REST 로 조회 — 피드가 붙어 있으면 KiwoomDataClient 가 캐시를 먼저 본다).
    state 를 안 주면 매 호출이 독립적이다(단발 호출·테스트 호환).
    """
    if state is None:
        state = MonitorState()

    # 유지보수(housekeeping)는 각 단계를 격리한다 — 한 단계가 실패해도 아래 하드손절/스탑
    # 감시(자금 안전의 핵심)는 반드시 돈다. 과거 reconcile_dead_sent 의 멱등키 충돌 예외가
    # check_once 전체를 매 폴링 중단시켜 모든 종목 감시가 멈췄던 회귀를 막는다.
    #  - 체결 동기화: live 체결을 포지션에 반영(paper no-op)
    #  - 잔여 미체결 취소: 전일 잔여 미체결 자동 취소(개장 중 묶임 방지)
    #  - 죽은 주문 정리: 0주 체결로 소멸한 'sent' 주문 정리 + 멱등키 해제(같은 tag 재매도 허용)
    for label, step in (("체결 동기화", sync_fills),
                        ("잔여 미체결 취소", cancel_stale_orders),
                        ("죽은 주문 정리", reconcile_dead_sent)):
        try:
            step(engine.client)
        except Exception as e:
            logger.error("%s 실패(감시는 계속 진행): %s", label, e)

    state.refresh()
    hard_pct = effective_hard_stop_pct()  # 오버나잇 US 급락이면 기본보다 좁게(보수적)

    # plan 은 있는데 포지션이 사라진 경우 정리
    for stk_cd, plan in list(state.plans.items()):
        if stk_cd not in state.positions:
            plan_repo.deactivate(plan["trade_date"], stk_cd, "이미 청산됨")
            state.plans.pop(stk_cd, None)  # 스냅샷에서도 제거(틱 경로가 죽은 plan 을 안 보게)

    # 보유 포지션마다 현재가 1회 조회 → 하드 손절(평단 대비) → 스탑선(settle_plan) 순으로 점검
    for stk_cd, pos in list(state.positions.items()):
        if pos["qty"] < 1:
            continue
        try:
            cur = engine.data.get_market_price(stk_cd)
            if cur <= 0:
                continue
            _evaluate_position(engine, state, stk_cd, pos, cur, hard_pct,
                               datetime.now(), allow_trail=True, path="slow")
        except Exception as e:
            logger.error("모니터 점검 실패 [%s]: %s", stk_cd, e)

    state.last_slow_ts = time.time()


def check_ticks(engine: ExecutionEngine, state: MonitorState, feed) -> None:
    """WS 틱 즉시 판정 — 뉴스베토·하드손절·스탑 breach 만(트레일링 상향 제외).

    DB 를 읽지 않고 스냅샷 + 캐시 가격으로만 판정한다. 해당 보드의 신선한 틱이 없는
    종목(미구독·NXT 불가·체결 없는 하한가·WS 끊김)은 건너뛰고, 15초 경로가 REST 로 본다.
    """
    hard_pct = effective_hard_stop_pct()  # 프로세스당 1회 계산·캐시
    now = datetime.now()
    prefer_nxt = not _in_krx_session(now)
    for stk_cd, pos in list(state.positions.items()):
        if pos["qty"] < 1:
            continue
        try:
            cur = feed.get_fresh(stk_cd, prefer_nxt=prefer_nxt)
            if not cur or cur <= 0:
                continue
            _evaluate_position(engine, state, stk_cd, pos, cur, hard_pct,
                               now, allow_trail=False, path="tick")
        except Exception as e:
            logger.error("틱 판정 실패 [%s]: %s", stk_cd, e)


def _start_feed(engine: ExecutionEngine):
    """보유 종목의 NXT 여부를 1회 조회해 실시간 구독을 시작한다.

    실패하면 None — 순수 15초 폴링(종전 동작)으로 계속한다. 여기서 종목별
    is_nxt_enabled 를 한 번만 조회하므로, 폴링마다 반복하던 ka10100 호출도 사라진다."""
    if not REALTIME_FEED_ENABLED:
        logger.info("실시간 피드 비활성(REALTIME_FEED_ENABLED=0) — 15초 폴링만 사용")
        return None
    try:
        from core.realtime_feed import KiwoomRealtimeFeed

        symbols = {}
        for p in position_repo.get_open_positions():
            if p["qty"] >= 1:
                symbols[p["stk_cd"]] = engine.data.is_nxt_enabled(p["stk_cd"])
        feed = KiwoomRealtimeFeed(symbols=symbols)
        feed.start()
        engine.data.attach_feed(feed)
        logger.info("실시간 피드 시작 — %d종목 구독 %s", len(symbols), symbols)
        audit_log.append("monitor_feed_start", None, {"symbols": symbols})
        return feed
    except Exception as e:
        logger.warning("실시간 피드 시작 실패 — 15초 폴링으로 계속: %s", e)
        return None


def _sync_feed_symbols(engine: ExecutionEngine, state: MonitorState, feed) -> None:
    """스냅샷에 새 종목이 생겼으면 구독에 추가(monitor 는 매수하지 않아 드문 경로)."""
    try:
        known = set(feed._symbols)  # noqa: SLF001 — 같은 도메인 내부 상태 확인
        new = [c for c in state.positions if c not in known]
        if not new:
            return
        merged = {**feed._symbols, **{c: engine.data.is_nxt_enabled(c) for c in new}}
        feed.set_symbols(merged)
        logger.info("실시간 구독 추가: %s", new)
    except Exception as e:
        logger.warning("구독 갱신 실패(감시는 계속): %s", e)


def main() -> int:
    if not in_window(datetime.now()):
        logger.info("가동 구간(평일 08:00~09:30) 밖 — 종료")
        return 0
    logger.info("하드손절(-%.1f%%)/스탑 모니터 시작 (틱 즉시 판정 + %d초 유지보수, "
                "08:00 기동, 08:00·09:00 워밍업 스킵, 09:30 자동 종료)",
                HARD_STOP_LOSS_PCT, POLL_SEC)
    audit_log.append("monitor_start", None, {
        "poll_sec": POLL_SEC, "hard_stop_pct": HARD_STOP_LOSS_PCT, "trail_pct": TRAIL_PCT,
        "tick_wait_sec": MONITOR_TICK_WAIT_SEC, "sell_cooldown_sec": SELL_RETRY_COOLDOWN_SEC})
    engine = ExecutionEngine()
    state = MonitorState()
    feed = _start_feed(engine)
    last_slow = 0.0
    try:
        while in_window(datetime.now()):
            now = datetime.now()
            if in_open_warmup(now):
                logger.info("개장 워밍업 %02d:%02d — 시가 체결 전 stale 가격 오발동 방지 위해 평가 스킵",
                            now.hour, now.minute)
                _beat({"warmup": True})
                time.sleep(POLL_SEC)
                continue

            # ── 15초 주기: 유지보수 + 스냅샷 갱신 + 트레일링 상향 + 하트비트 ──
            if time.time() - last_slow >= POLL_SEC:
                try:
                    check_once(engine, state)
                except Exception as e:
                    logger.error("모니터 루프 오류: %s", e)
                last_slow = time.time()
                beat = {"positions": len(state.positions),
                        "cooldown_skips": state.cooldown_skips}
                if feed is not None:
                    beat["ws"] = feed.stats()
                    _sync_feed_symbols(engine, state, feed)
                _beat(beat)

            if feed is None:
                time.sleep(POLL_SEC)  # 피드 없음 → 종전 15초 폴링 그대로
                continue

            # ── 체결통보(WS 00) 수신 시 즉시 체결 동기화 — 15초를 기다리지 않는다 ──
            if feed.take_fill_signal():
                try:
                    sync_fills(engine.client)
                    state.refresh()
                except Exception as e:
                    logger.error("체결통보 동기화 실패(감시는 계속): %s", e)

            # ── 틱 대기 후 즉시 판정(틱이 없어도 MONITOR_TICK_WAIT_SEC 마다 점검) ──
            feed.wait_for_tick(MONITOR_TICK_WAIT_SEC)
            try:
                check_ticks(engine, state, feed)
            except Exception as e:
                logger.error("틱 판정 루프 오류: %s", e)
    finally:
        if feed is not None:
            feed.stop()
            logger.info("실시간 피드 종료: %s", feed.stats())
    logger.info("가동 구간 종료 — 모니터 종료")
    audit_log.mark_worker_done("monitor")  # watchdog 완료 마커(미실행 감시)
    return 0


if __name__ == "__main__":
    from core.market_calendar import exit_if_not_trading_day
    # cron 은 평일만 돌지만 평일 공휴일(휴장)은 못 거른다 — 진입부에서 한 번 더 차단.
    exit_if_not_trading_day()
    main()
