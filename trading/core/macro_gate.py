"""거시 이벤트 게이트 — 보유 창(매수→익일 시가)에 걸린 '예정 거시 이벤트'로 총 시드 축소(reduce-only).

[근거] 종가베팅 손익은 익일 갭에 좌우되는데, FOMC 성명(03:00 KST)·미 CPI/고용보고서(21:30 KST)는
  보유 중 밤사이에 떨어지는 이진 이벤트다. 방향은 알 수 없지만 '결과에 갭이 걸려 있다'는 사실만으로
  기대손익이 나빠진다. 2026-07-15 백테스트(4/9~7/10 63거래일): severity 3 이벤트 밤 선정종목
  일평균 -0.74% vs 평일 +1.04%(Welch t=-2.27, 급락 레짐 혼재일 6/5 제외해도 t=-2.13, 음수일 62% vs 25%)
  → sev3 만 live 감액. PPI(sev2)는 오히려 +3.6%로 감액 근거 없음 → 관찰 전용(진단 기록만).
  futures_gate 가 '이미 실현된 선물 방향'을 재는 것과 상보적 — 발표 전엔 선물이 보합이라 저건 못 잡는다.

[지표] jongalab DB macro_event(수동 시드 캘린더, sql/18. migrate_macro_event.sql — 2026 연말까지).
  창 = 매수 시점(now) → 다음 평일 09:00 KST(익일 시가 매도). severity>=3 이벤트가 창에 있으면
  keep = MACRO_EVENT_KEEP(기본 0.5), 아니면 1.0. 금통위(09:50)는 시가 매도 후라 자연히 창 밖.
  캘린더 고갈은 jongalab macro_event_check 잡이 주 1회 감시(고갈 임박 시 텔레그램 경보).

[관찰 축] VIX 레벨·WTI 급등률·원달러 급등률(jongalab market-indices) — 호르무즈류 지정학 쇼크 프록시.
  keep 을 계산해 진단에만 남기고 **감액엔 적용하지 않는다**(임계 미검증). 축끼리는 min(같은 쇼크가
  세 축에 동시 반영되므로 곱이면 이중 감액). 승격 시에도 futures_gate 와 곱이 아니라 min 결합으로
  붙일 것 — 선물 급락과 VIX 급등은 같은 사건이다.

⛔ **이 프록시는 지금 설계대로 live 승격하면 안 된다** (2026-08-03 백테스트, 4/9~7/31 75거래일,
  selected 일평균 next_open_ret vs yfinance 일봉 복원 — market_snapshot.wti_ret 은 7/24부터라 표본 부족):
  · VIX 축은 **부호가 반대**다. 여기 램프는 VIX 가 높을수록 깎는데, 실측은 VIX 가 높을수록 익일
    성적이 좋다(전체 corr +0.318, t=+2.87 / 상위⅓ +1.77% vs 하위⅓ +0.06%). 지금 설계대로 켜면
    담아야 할 때 깎는다. 단 월별로 5월 t=-3.13, 6월 t=+3.96 로 불안정해 **역방향 승격도 근거 없다**
    — 부호를 재검정하기 전까지 관찰 전용 유지가 결론. 참고로 표본 기간 VIX>=20 은 3일뿐이라
    임계 25 는 한 번도 발동한 적이 없다(휴면).
  · WTI 축은 **기각**. 매수 시점 가용값(전일 등락)은 corr -0.051(t=-0.44)이고, 우리가 실제로 들고
    있는 그 밤의 WTI 변동조차 corr +0.050(t=+0.42)로 무관계다 — 같은 창에서 NQ 선물은 t=+3.69.
    유니버스가 지수 대형주(중위 시총 9.8조)여도 상위가 반도체라 갭 전달 경로는 유가가 아니라 미
    기술주 축이고, 그건 futures_gate 가 이미 잡는다. 충격 크기 컷(|WTI|>=N%p)도 N=2/3/4 에서
    t=-0.65/-1.58/-0.13 으로 비단조 + 7월 부호 반전(임계 쇼핑). 섹터 분해 중 운송장비/부품만
    부호가 맞으나(t=-1.78) 미달 — 유가를 쓰려면 총 시드 축이 아니라 그 섹터 rule 로 가야 한다.
  세 축 원값(vix_level/wti_pct/fx_pct)은 계속 진단에 남긴다 — 위 재검정·섹터 연구의 표본이다.
  → [[oil-war-axis-rejected-0803]]

[안전] 캘린더 조회 실패 → 미개입(1.0, 다른 게이트와 동일하게 '불확실하면 축소하지 않는다').
  프록시 취득 실패 → 진단 null(감액 무영향). 매 판단(미개입 포함)을 signal_executor 가
  audit_log('macro_gate') 로 남긴다 — 사후 채점·재튜닝용.
"""
import logging
from datetime import datetime, time, timedelta

import requests

from core.db import get_jongalab_db
from core.config import (
    MACRO_GATE_ENABLED,
    MACRO_EVENT_KEEP,
    MACRO_VIX_LO,
    MACRO_VIX_HI,
    MACRO_WTI_BAND,
    MACRO_WTI_FULL,
    MACRO_FX_BAND,
    MACRO_FX_FULL,
    MACRO_PROXY_MAX_CUT,
    JONGALAB_BASE_URL,
)

logger = logging.getLogger("MacroGate")

_HTTP_TIMEOUT = 5
# market-indices 그룹/심볼 — jongalab core/market_data.py MARKET_INDICES 정의와 동기.
_PROXY_SYMBOLS = {"vix": ("US", "^VIX"), "wti": ("COMMODITIES", "CL=F"), "fx": ("KR", "USDKRW=X")}


def _window_end(now: datetime) -> datetime:
    """보유 창의 끝 = 다음 평일 09:00 KST(익일 시가 매도 시점). 주말은 건너뛴다.

    한계: 평일 공휴일은 미반영(그날 매도 못 하면 실제 보유가 하루 더 길다) — 드문 편차라 수용.
    """
    d = now.date() + timedelta(days=1)
    while d.weekday() >= 5:  # 5=토, 6=일
        d += timedelta(days=1)
    return datetime.combine(d, time(9, 0))


def _upcoming_events(start: datetime, end: datetime) -> list[dict]:
    """창 (start, end] 안의 macro_event 행들(severity 내림차순)."""
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT event_time, name, category, severity FROM macro_event "
            "WHERE event_time > %s AND event_time <= %s ORDER BY severity DESC, event_time",
            (start, end),
        )
        return cursor.fetchall()


def _events_keep(events: list[dict]) -> float:
    """severity 3 이벤트가 하나라도 있으면 MACRO_EVENT_KEEP, 아니면 1.0(sev2 이하는 관찰 전용)."""
    if any(int(e["severity"]) >= 3 for e in events):
        return MACRO_EVENT_KEEP
    return 1.0


def _ramp(value: float | None, lo: float, hi: float) -> float:
    """선형 강도 0~1 — value<=lo 에서 0, value>=hi 에서 1 (futures_gate _cut_intensity 와 동형)."""
    if value is None or value <= lo:
        return 0.0
    if hi <= lo:
        return 1.0
    return min(1.0, (value - lo) / (hi - lo))


def _proxy_state() -> tuple[dict | None, str]:
    """관찰용 프록시(VIX 레벨/WTI·환율 등락률) 취득 — market-indices 1회 호출."""
    try:
        resp = requests.get(f"{JONGALAB_BASE_URL}/api/market-indices", timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}
    except Exception as e:
        return None, f"proxy_http_error: {e}"

    def _find(group: str, symbol: str) -> dict:
        for item in data.get(group) or []:
            if item.get("symbol") == symbol:
                return item
        return {}

    vix = _find(*_PROXY_SYMBOLS["vix"]).get("price")
    wti = _find(*_PROXY_SYMBOLS["wti"]).get("change_percent")
    fx = _find(*_PROXY_SYMBOLS["fx"]).get("change_percent")
    return {
        "vix_level": float(vix) if vix is not None else None,
        "wti_pct": float(wti) if wti is not None else None,
        "fx_pct": float(fx) if fx is not None else None,
    }, "ok"


def _proxy_keep(state: dict) -> float:
    """관찰용 keep — 세 축은 같은 쇼크의 다른 얼굴이라 곱이 아닌 min(가장 강한 축 하나만).
    감액에 쓰지 않는다 — 진단 기록 전용.

    ⚠️ 이 값을 '승격하면 이만큼 깎였을 것'으로 읽지 말 것. 2026-08-03 검정에서 VIX 축은 부호가
    반대, WTI 축은 기각됐다(모듈 docstring ⛔ 절). 원값 vix_level/wti_pct/fx_pct 가 실제 표본이고,
    이 합성값은 그 위에 얹힌 미검증 매핑일 뿐이다."""
    intensities = (
        _ramp(state.get("vix_level"), MACRO_VIX_LO, MACRO_VIX_HI),
        _ramp(state.get("wti_pct"), MACRO_WTI_BAND, MACRO_WTI_FULL),
        _ramp(state.get("fx_pct"), MACRO_FX_BAND, MACRO_FX_FULL),
    )
    return round(min(1.0 - MACRO_PROXY_MAX_CUT * i for i in intensities), 3)


def month_events(month: str) -> list[dict]:
    """해당 월(YYYYMM)의 macro_event 목록 — 손익 달력 마커용(/macro-events).

    반환: [{date: "YYYYMMDD", time: "HH:MM", name, category, severity}] (시각순).
    """
    start = datetime.strptime(month, "%Y%m")
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT event_time, name, category, severity FROM macro_event "
            "WHERE event_time >= %s AND event_time < %s ORDER BY event_time",
            (start, end),
        )
        rows = cursor.fetchall()
    return [{"date": r["event_time"].strftime("%Y%m%d"),
             "time": r["event_time"].strftime("%H:%M"),
             "name": r["name"], "category": r["category"],
             "severity": int(r["severity"])} for r in rows]


def macro_keep(venue: str) -> tuple[float, dict]:
    """총 시드에 곱할 거시 이벤트 keep(≤1.0) + 진단을 반환.

    게이트 비활성/캘린더 조회 실패면 (1.0, gated=False) — 미개입.
    성공 시 창 안 이벤트 목록·관찰 프록시를 진단에 동봉(audit 스냅샷용).
    """
    if not MACRO_GATE_ENABLED:
        return 1.0, {"gated": False, "reason": "disabled"}

    now = datetime.now()
    end = _window_end(now)
    try:
        events = _upcoming_events(now, end)
    except Exception as e:
        logger.warning("macro_event 조회 실패 — 게이트 미개입(1.0): %s", e)
        return 1.0, {"gated": False, "reason": f"query_error: {e}"}

    keep = _events_keep(events)

    # 관찰 전용 프록시 — 실패해도 keep 에 영향 없음(진단 null)
    proxy, proxy_note = _proxy_state()
    proxy_diag = {"note": proxy_note}
    if proxy is not None:
        proxy_diag.update(proxy, keep_obs=_proxy_keep(proxy))

    diag = {
        "gated": True, "venue": venue, "keep": keep,
        "window_end": end.strftime("%Y-%m-%d %H:%M"),
        "events": [{"time": e["event_time"].strftime("%m-%d %H:%M"), "name": e["name"],
                    "severity": int(e["severity"])} for e in events],
        "proxy": proxy_diag,
    }
    if keep < 1.0:
        names = ", ".join(e["name"] for e in events if int(e["severity"]) >= 3)
        logger.info("거시 이벤트 게이트[%s]: 창(~%s) 내 %s → keep %.3f",
                    venue, diag["window_end"], names, keep)
    else:
        logger.info("거시 이벤트 게이트[%s]: 창(~%s) 내 sev3 없음(이벤트 %d건) — 감액 없음",
                    venue, diag["window_end"], len(events))
    return keep, diag
