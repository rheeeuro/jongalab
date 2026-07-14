"""macro_gate 단위 테스트 — 거시 이벤트 게이트의 순수 로직 고정(DB·HTTP 미접근).

불변식:
  - _window_end: 다음 평일 09:00 (주말 건너뜀)
  - _events_keep: sev3 존재 → MACRO_EVENT_KEEP / sev2 이하만 → 1.0(관찰 전용)
  - _ramp: lo 이하 0, hi 이상 1, 사이 선형
  - _proxy_keep: 축 간 min 결합(곱 아님 — 같은 쇼크 이중 감액 방지), 관찰 전용
  - macro_keep: 비활성/조회 실패 → 1.0(미개입) / 프록시 실패는 keep 무영향
"""
from datetime import datetime

import core.macro_gate as mg


def test_window_end_weekday():
    # 수요일 저녁 매수 → 목요일 09:00
    assert mg._window_end(datetime(2026, 7, 15, 19, 50)) == datetime(2026, 7, 16, 9, 0)


def test_window_end_skips_weekend():
    # 금요일 매수 → 월요일 09:00 (토·일 건너뜀)
    assert mg._window_end(datetime(2026, 7, 17, 15, 20)) == datetime(2026, 7, 20, 9, 0)


def test_events_keep_sev3_cuts():
    events = [{"severity": 2}, {"severity": 3}]
    assert mg._events_keep(events) == mg.MACRO_EVENT_KEEP


def test_events_keep_sev2_observe_only():
    # PPI(sev2)는 백테스트상 감액 근거 없음 — 관찰 전용
    assert mg._events_keep([{"severity": 2}]) == 1.0
    assert mg._events_keep([]) == 1.0


def test_ramp_linear():
    assert mg._ramp(None, 25, 35) == 0.0
    assert mg._ramp(25.0, 25, 35) == 0.0
    assert mg._ramp(30.0, 25, 35) == 0.5
    assert mg._ramp(40.0, 25, 35) == 1.0


def test_proxy_keep_min_not_product():
    # 두 축이 동시에 최대 강도여도 min 결합 — 한 축 최대컷만큼만 (곱이면 이중 감액)
    state = {"vix_level": mg.MACRO_VIX_HI, "wti_pct": mg.MACRO_WTI_FULL, "fx_pct": None}
    assert mg._proxy_keep(state) == round(1.0 - mg.MACRO_PROXY_MAX_CUT, 3)


def test_macro_keep_sev3_event(monkeypatch):
    ev = [{"event_time": datetime(2026, 7, 30, 3, 0), "name": "FOMC 금리결정",
           "category": "rate", "severity": 3}]
    monkeypatch.setattr(mg, "_upcoming_events", lambda s, e: ev)
    monkeypatch.setattr(mg, "_proxy_state", lambda: (None, "off"))
    keep, diag = mg.macro_keep("nxt")
    assert keep == mg.MACRO_EVENT_KEEP
    assert diag["gated"] is True and diag["events"][0]["severity"] == 3


def test_macro_keep_sev2_no_cut_but_recorded(monkeypatch):
    ev = [{"event_time": datetime(2026, 7, 15, 21, 30), "name": "미 PPI",
           "category": "inflation", "severity": 2}]
    monkeypatch.setattr(mg, "_upcoming_events", lambda s, e: ev)
    monkeypatch.setattr(mg, "_proxy_state", lambda: (None, "off"))
    keep, diag = mg.macro_keep("krx")
    assert keep == 1.0
    assert diag["gated"] is True and len(diag["events"]) == 1  # 관찰 기록은 남는다


def test_macro_keep_query_error_no_intervention(monkeypatch):
    def _boom(s, e):
        raise RuntimeError("db down")
    monkeypatch.setattr(mg, "_upcoming_events", _boom)
    keep, diag = mg.macro_keep("nxt")
    assert keep == 1.0 and diag["gated"] is False and "query_error" in diag["reason"]


def test_macro_keep_proxy_failure_does_not_affect_keep(monkeypatch):
    monkeypatch.setattr(mg, "_upcoming_events", lambda s, e: [])
    monkeypatch.setattr(mg, "_proxy_state", lambda: (None, "proxy_http_error: boom"))
    keep, diag = mg.macro_keep("nxt")
    assert keep == 1.0 and diag["gated"] is True
    assert "keep_obs" not in diag["proxy"]  # 취득 실패 시 관찰값도 미기록(null 진단)


def test_macro_keep_proxy_observed_only(monkeypatch):
    # 프록시가 극단이어도 적용 keep 은 캘린더 축만 따른다(관찰 전용)
    monkeypatch.setattr(mg, "_upcoming_events", lambda s, e: [])
    monkeypatch.setattr(mg, "_proxy_state",
                        lambda: ({"vix_level": 99.0, "wti_pct": 99.0, "fx_pct": 99.0}, "ok"))
    keep, diag = mg.macro_keep("nxt")
    assert keep == 1.0
    assert diag["proxy"]["keep_obs"] == round(1.0 - mg.MACRO_PROXY_MAX_CUT, 3)


def test_macro_keep_disabled(monkeypatch):
    monkeypatch.setattr(mg, "MACRO_GATE_ENABLED", False)
    keep, diag = mg.macro_keep("nxt")
    assert keep == 1.0 and diag["gated"] is False
