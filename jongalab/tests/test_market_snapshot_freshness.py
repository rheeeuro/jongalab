"""연구 스냅샷 신선도 가드 계약 — `_drop_stale_us_bars` · `night_ret_if_fresh`.

둘 다 같은 문제를 막는다: **등락률만 보면 결함을 알 수 없다.** yfinance 가 최근 봉을 빠뜨리거나
야간선물 스트림이 끊기면 옛 세션 값이 당일 값으로 채점 표본에 들어간다(기준가가 다른 값이
같은 컬럼에 섞인다). 표시 경로는 근사값으로 버티는 게 맞지만 채점 경로는 NULL 이 맞다.
"""
from datetime import date

from core.market_data import _drop_stale_us_bars, night_ret_if_fresh, _NIGHT_FUT_STALE_SEC

D18, D20, D21 = date(2026, 8, 18), date(2026, 8, 20), date(2026, 8, 21)


def _q(symbol: str, pct: float | None, bar_date: date | None) -> dict:
    return {"symbol": symbol, "price": 100.0, "change_percent": pct, "bar_date": bar_date}


def _batch(**overrides: dict) -> dict[str, dict]:
    """미국 정규장 6심볼이 모두 같은 날 봉을 가진 정상 배치 + 덮어쓸 항목."""
    batch = {s: _q(s, 1.0, D20) for s in ("^GSPC", "^SOX", "^VIX", "EWY", "KORU", "SKHY")}
    batch.update(overrides)
    return batch


def test_stale_symbol_is_dropped():
    """기준(최빈) 날짜보다 뒤처진 심볼은 값을 버린다 — 틀린 값보다 NULL 이 낫다."""
    q = _batch(**{"^SOX": _q("^SOX", -4.78, D18)})
    _drop_stale_us_bars(q)
    assert q["^SOX"]["change_percent"] is None
    assert q["^SOX"]["price"] is None
    assert q["^GSPC"]["change_percent"] == 1.0  # 정상 심볼은 그대로


def test_symbol_ahead_of_mode_survives():
    """기준보다 **앞선** 심볼은 버리지 않는다 — ^VIX 는 미국 확장 세션에 당일 봉이 먼저 생긴다.

    앞선 심볼을 기준으로 삼으면(최빈값 대신 최댓값) 정상인 나머지 5개가 통째로 날아간다.
    """
    q = _batch(**{"^VIX": _q("^VIX", None, D21)})
    _drop_stale_us_bars(q)
    assert q["^VIX"]["price"] == 100.0
    assert all(q[s]["change_percent"] == 1.0 for s in ("^GSPC", "^SOX", "EWY", "KORU", "SKHY"))


def test_non_us_session_symbols_are_untouched():
    """24시간 심볼(선물·환율)은 대상이 아니다 — 한국 오후에 당일 봉이 이미 진행 중이다."""
    q = _batch()
    q["NQ=F"] = _q("NQ=F", -9.9, D21)
    q["USDKRW=X"] = _q("USDKRW=X", 0.5, D21)
    _drop_stale_us_bars(q)
    assert q["NQ=F"]["change_percent"] == -9.9
    assert q["USDKRW=X"]["change_percent"] == 0.5


def test_no_intervention_when_sample_too_small():
    """비교 표본이 3개 미만이면 최빈값을 신뢰할 수 없으므로 미개입(값 보존)."""
    q = {"^SOX": _q("^SOX", -4.78, D18), "^GSPC": _q("^GSPC", 1.0, D20)}
    _drop_stale_us_bars(q)
    assert q["^SOX"]["change_percent"] == -4.78


def test_missing_bar_date_is_not_dropped():
    """봉 날짜를 못 얻은 심볼(조회 실패)은 이미 값이 없으므로 판정 대상이 아니다."""
    q = _batch(**{"^SOX": _q("^SOX", None, None)})
    _drop_stale_us_bars(q)
    assert q["^SOX"]["change_percent"] is None
    assert q["^GSPC"]["change_percent"] == 1.0


# ── 야간선물 축 신선도 (`night_ret_if_fresh`) ──
# 기준가가 그날 주간 정산가라, 세션 밖 값을 저장하면 **기준가가 다른 값**이 같은 컬럼에 섞인다.


def test_night_ret_fresh_value_passes():
    assert night_ret_if_fresh({"change_percent": -0.53, "age_sec": 12}) == -0.53


def test_night_ret_stale_value_is_dropped():
    """세션 밖/스트림 단절 값은 버린다 — 직전 세션 종가라 기준가가 다르다."""
    assert night_ret_if_fresh({"change_percent": -0.53,
                               "age_sec": _NIGHT_FUT_STALE_SEC + 1}) is None


def test_night_ret_boundary_is_inclusive():
    """임계값 자체는 통과 — 경계에서 값이 사라지지 않게(게이트와 같은 눈금)."""
    assert night_ret_if_fresh({"change_percent": 1.0,
                               "age_sec": _NIGHT_FUT_STALE_SEC}) == 1.0


def test_night_ret_missing_row_or_value():
    assert night_ret_if_fresh(None) is None
    assert night_ret_if_fresh({"change_percent": None, "age_sec": 1}) is None
