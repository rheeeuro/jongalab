"""futures_gate 단위 테스트 — 선물 섹터 게이트의 순수 로직 고정(DB/HTTP 미접근).

불변식:
  - _bearish: 등락률이 -FLAT_BAND 미만이면 하락(band 이내 보합·상승·None 은 False)
  - _class_of: 업종명→클래스, 미매핑/None→neutral
  - _sector_keep: 하락 축에만 감액, 항상 ≤1.0, 하한 MIN_KEEP. 고베타(tech)를 방어주보다 더 깎음
  - sector_keep_factors: 대상 아님/취득 실패→({}, gated=False) / 성공→전 종목 keep(≤1.0)
"""
import core.futures_gate as fg


def test_bearish_band():
    b = fg.FUTURES_FLAT_BAND
    assert fg._bearish(-(b + 0.5)) is True
    assert fg._bearish(-b) is False           # 경계(보합)
    assert fg._bearish(0.0) is False
    assert fg._bearish(1.0) is False          # 상승
    assert fg._bearish(None) is False         # 취득 실패


def test_class_mapping():
    assert fg._class_of("전기/전자") == "tech"
    assert fg._class_of("화학") == "cyclical"
    assert fg._class_of("금융") == "financial"
    assert fg._class_of("통신") == "defensive"
    assert fg._class_of("제약") == "indep"
    assert fg._class_of("존재하지않는업종") == "neutral"
    assert fg._class_of(None) == "neutral"


def test_sector_keep_no_cut_when_up():
    # 둘 다 상승 → 감액 없음
    assert fg._sector_keep("전기/전자", 1.0, 0.5) == 1.0


def test_gated_shares_rounds_not_floors():
    # mild 컷(keep>=0.5)은 1주짜리를 0으로 없애지 않는다(반올림). keep<0.5 만 0 가능.
    assert fg.gated_shares(1, 0.9) == 1       # 예전 int() 면 0 이었음
    assert fg.gated_shares(1, 0.5) == 1
    assert fg.gated_shares(1, 0.3) == 0       # 절반 넘게 컷이면 0 가능
    assert fg.gated_shares(12, 0.5) == 6
    assert fg.gated_shares(1, 1.0) == 1       # 감액 없음
    # reduce-only: 절대 원래보다 많지 않다
    for sh in (1, 3, 10, 25):
        for k in (0.25, 0.5, 0.85, 0.99):
            assert fg.gated_shares(sh, k) <= sh


def test_cut_scales_with_magnitude():
    # 같은 tech 라도 NQ 낙폭이 클수록 더 깎인다(작은 하락<큰 하락). 상승/보합은 감액 0.
    small = fg._sector_keep("전기/전자", -0.5, 0.3)
    big = fg._sector_keep("전기/전자", -2.5, 0.3)
    flat = fg._sector_keep("전기/전자", -0.05, 0.3)  # 밴드 이내 → 감액 없음
    assert flat == 1.0
    assert big < small < 1.0
    # 작은 하락(-0.5%)은 예전 이진 컷(×0.5)보다 훨씬 덜 깎여야 한다
    assert small > 0.5


def test_cut_intensity_clamps():
    assert fg._cut_intensity(0.5) == 0.0            # 상승
    assert fg._cut_intensity(-0.05) == 0.0          # 보합밴드 이내
    assert fg._cut_intensity(-fg.FUTURES_FULL_CUT_PCT - 5) == 1.0  # 급락 → 상한 1.0
    assert 0.0 < fg._cut_intensity(-0.5) < 1.0      # 중간


def test_sector_keep_reduce_only_and_floor():
    # 강한 하락에도 keep 은 MIN_KEEP 이상, 1.0 이하
    k = fg._sector_keep("전기/전자", -5.0, -5.0)
    assert fg.FUTURES_SECTOR_MIN_KEEP <= k <= 1.0


def test_tech_cut_more_than_defensive_when_nq_down():
    # NQ 하락 시 반도체/IT(고 NQ민감)를 방어주보다 더 깎는다
    tech = fg._sector_keep("전기/전자", -1.5, 0.5)
    defensive = fg._sector_keep("통신", -1.5, 0.5)
    assert tech < defensive <= 1.0


def test_cyclical_cut_more_than_tech_when_only_index_down():
    # 코스피200만 하락 시 경기민감주(자동차·화학)를 반도체보다 더 깎는다
    cyclical = fg._sector_keep("화학", 0.5, -1.2)
    tech = fg._sector_keep("전기/전자", 0.5, -1.2)
    assert cyclical < tech <= 1.0


def test_effective_keep_combined_floor():
    floor = fg.SEED_COMBINED_MIN_MULT
    # 레짐 정상(1.0): raw 그대로, 단 결합 하한 밑이면 끌어올림
    assert fg.effective_keep(0.375, 1.0) == 0.375
    assert fg.effective_keep(0.2, 1.0) == floor          # raw<floor → floor 로
    # 레짐이 하한과 같으면(0.3): 추가 감액 불가 → 1.0 (결합이 이미 하한)
    assert fg.effective_keep(0.375, floor) == 1.0
    # 레짐 mild(0.6): 결합이 하한 밑으로 안 가게 clamp → 0.6×keep>=floor
    k = fg.effective_keep(0.375, 0.6)
    assert round(0.6 * k, 3) >= floor and k <= 1.0
    # 상승(raw=1.0)이면 감액 없음
    assert fg.effective_keep(1.0, 0.6) == 1.0


def test_keep_factors_venue_not_targeted(monkeypatch):
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    factors, diag = fg.sector_keep_factors("krx", ["005930"])
    assert factors == {} and diag["gated"] is False and diag["reason"].startswith("venue_skip")


def _state(ok, nq, kospi, label="야간선물"):
    return {"ok": ok, "nq_pct": nq, "kospi_pct": kospi, "kospi_label": label,
            "nq_note": "ok", "kospi_note": "ok"}


def test_keep_factors_unavailable(monkeypatch):
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(False, None, -1.0))
    factors, diag = fg.sector_keep_factors("nxt", ["005930"])
    assert factors == {} and diag["gated"] is False and diag["reason"] == "unavailable"


def test_keep_factors_both_down_differentiates_sectors(monkeypatch):
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, -1.5, -1.2))
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {
        "AAA": "전기/전자", "BBB": "통신", "CCC": None})
    factors, diag = fg.sector_keep_factors("nxt", ["AAA", "BBB", "CCC"])
    assert diag["gated"] is True and diag["nq_down"] and diag["kospi_down"]
    # 전 종목 keep 반환, tech(AAA) < neutral(CCC) < defensive(BBB) 순으로 더 깎임
    assert set(factors) == {"AAA", "BBB", "CCC"}
    assert all(v <= 1.0 for v in factors.values())
    assert factors["AAA"] < factors["BBB"]
    assert factors["AAA"] < factors["CCC"]


def test_keep_factors_krx_uses_day_future(monkeypatch):
    # KRX 도 게이트 적용 — 주간선물 축으로 감액, diag 라벨/필드 확인
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"krx", "nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, -1.5, -1.2, label="주간선물"))
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {"AAA": "전기/전자"})
    factors, diag = fg.sector_keep_factors("krx", ["AAA"])
    assert diag["gated"] is True and diag["venue"] == "krx" and diag["kospi_label"] == "주간선물"
    assert factors["AAA"] < 1.0


def test_keep_factors_all_up_no_cut(monkeypatch):
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, 0.8, 0.5))
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {"AAA": "전기/전자"})
    factors, diag = fg.sector_keep_factors("nxt", ["AAA"])
    assert diag["gated"] is True and factors["AAA"] == 1.0  # 상승이면 감액 없음
