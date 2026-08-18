"""futures_gate 단위 테스트 — 선물 섹터 게이트의 순수 로직 고정(DB/HTTP 미접근).

불변식:
  - _bearish: 등락률이 -FLAT_Z×σ 미만이면 하락(밴드 이내 보합·상승·None 은 False)
  - _cut_intensity: 강도는 축의 σ 로 정규화한 z 기준 — 같은 %p 라도 σ 가 크면 약하게 반응
  - _class_of: 업종명→클래스, 미매핑/None→neutral
  - _sector_keep: 하락 축에만 감액, 항상 ≤1.0, 하한 MIN_KEEP. 고베타(tech)를 방어주보다 더 깎음
  - sector_keep_factors: 대상 아님/취득 실패→({}, gated=False) / 성공→전 종목 keep(≤1.0)
"""
import core.futures_gate as fg

_SD = fg.FUTURES_SD_K200_NIGHT   # 테스트 기본 코스피 축 σ(야간선물)


def test_bearish_band():
    b = fg.FUTURES_FLAT_Z * _SD
    assert fg._bearish(-(b + 0.5), _SD) is True
    assert fg._bearish(-b, _SD) is False           # 경계(보합)
    assert fg._bearish(0.0, _SD) is False
    assert fg._bearish(1.0, _SD) is False          # 상승
    assert fg._bearish(None, _SD) is False         # 취득 실패


def test_bearish_band_scales_with_sd():
    """같은 -1.0%p 가 σ 작은 축(NQ)에선 하락, σ 큰 축(주간선물)에선 보합이다."""
    assert fg._bearish(-1.0, fg.FUTURES_SD_NQ) is True           # 1.11σ
    assert fg._bearish(-1.0, fg.FUTURES_SD_K200_DAY) is False    # 0.16σ — 노이즈


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
    assert fg._sector_keep("전기/전자", 1.0, 0.5, _SD) == 1.0


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
    small = fg._sector_keep("전기/전자", -0.5, 0.3, _SD)
    big = fg._sector_keep("전기/전자", -2.5, 0.3, _SD)
    flat = fg._sector_keep("전기/전자", -0.05, 0.3, _SD)  # 밴드 이내 → 감액 없음
    assert flat == 1.0
    assert big < small < 1.0
    # 작은 하락(-0.5%)은 예전 이진 컷(×0.5)보다 훨씬 덜 깎여야 한다
    assert small > 0.5


def test_cut_intensity_clamps():
    assert fg._cut_intensity(0.5, _SD) == 0.0            # 상승
    assert fg._cut_intensity(-0.05, _SD) == 0.0          # 보합밴드 이내
    assert fg._cut_intensity(-fg.FUTURES_FULL_Z * _SD - 5, _SD) == 1.0  # 급락 → 상한 1.0
    assert 0.0 < fg._cut_intensity(-0.5, _SD) < 1.0      # 중간
    assert fg._cut_intensity(-5.0, 0.0) == 0.0           # σ 미지 → 미개입


def test_cut_intensity_normalized_by_sd():
    """축별 눈금 정규화의 핵심 — 같은 -2.0%p 가 σ 에 따라 다른 강도가 된다.

    구 로직(절대 FULL_CUT_PCT=2.0 공유)에선 셋 다 강도 1.0(최대컷)이었다. 특히 주간선물은
    σ 6.3 이라 -2%p 가 일상 변동(0.32σ)인데도 최대컷이 나가 -2%와 -6%를 구분하지 못했다.
    """
    i_nq = fg._cut_intensity(-2.0, fg.FUTURES_SD_NQ)            # 2.22σ → 최대
    i_night = fg._cut_intensity(-2.0, fg.FUTURES_SD_K200_NIGHT)  # 1.25σ → 중간
    i_day = fg._cut_intensity(-2.0, fg.FUTURES_SD_K200_DAY)      # 0.32σ → 미미
    assert i_nq == 1.0
    assert 0.0 < i_day < i_night < 1.0
    # 주간선물 축은 낙폭이 커져야 최대컷에 닿는다(비례성 복원)
    assert fg._cut_intensity(-2.0, fg.FUTURES_SD_K200_DAY) < \
        fg._cut_intensity(-6.0, fg.FUTURES_SD_K200_DAY) < 1.0


def test_sector_keep_reduce_only_and_floor():
    # 강한 하락에도 keep 은 MIN_KEEP 이상, 1.0 이하
    k = fg._sector_keep("전기/전자", -5.0, -5.0, _SD)
    assert fg.FUTURES_SECTOR_MIN_KEEP <= k <= 1.0


def test_tech_cut_more_than_defensive_when_nq_down():
    # NQ 하락 시 반도체/IT(고 NQ민감)를 방어주보다 더 깎는다
    tech = fg._sector_keep("전기/전자", -1.5, 0.5, _SD)
    defensive = fg._sector_keep("통신", -1.5, 0.5, _SD)
    assert tech < defensive <= 1.0


def test_cyclical_cut_more_than_tech_when_only_index_down():
    # 코스피200만 하락 시 경기민감주(자동차·화학)를 반도체보다 더 깎는다
    cyclical = fg._sector_keep("화학", 0.5, -1.2, _SD)
    tech = fg._sector_keep("전기/전자", 0.5, -1.2, _SD)
    assert cyclical < tech <= 1.0


def test_effective_keep_combined_floor():
    floor = fg.SEED_COMBINED_MIN_MULT
    # 하한 위면 선물×거시 곱 그대로
    assert fg.effective_keep(0.375) == 0.375
    # 하한 밑으로는 안 내려간다(두 게이트가 겹쳐도 최소 floor 는 산다)
    assert fg.effective_keep(0.2) == floor
    assert fg.effective_keep(0.0) == floor
    # 상승·보합(1.0 이상)이면 감액 없음
    assert fg.effective_keep(1.0) == 1.0
    assert fg.effective_keep(1.5) == 1.0


def test_keep_factors_venue_not_targeted(monkeypatch):
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    factors, diag = fg.sector_keep_factors("krx", ["005930"])
    assert factors == {} and diag["gated"] is False and diag["reason"].startswith("venue_skip")


def _state(ok, nq, kospi, label="야간선물", kospi_sd=fg.FUTURES_SD_K200_NIGHT):
    return {"ok": ok, "nq_pct": nq, "kospi_pct": kospi, "kospi_label": label,
            "kospi_sd": kospi_sd, "nq_note": "ok", "kospi_note": "ok"}


def _no_us_ext(monkeypatch):
    """US 확장 축을 끈다 — **선물 축만** 보려는 nxt 테스트에 필수.

    `_us_ext_signals()` 는 jongalab `/api/us-extended` 로 실제 HTTP 를 친다. 모킹을 빼면
    단위 테스트가 그 시각 미국장 상태에 좌우된다(2026-07-28: API 가 살아있고 market_state
    =PREPRE·SOXX -0.81 이라 `all_up_no_cut` 의 keep 이 1.0 대신 0.803 으로 나와 실패).
    US 축 자체를 검증하는 테스트는 아래에서 `_us_ext_signals` 를 직접 모킹한다."""
    monkeypatch.setattr(fg, "_us_ext_signals", lambda: {
        "semis_pct": None, "korea_pct": None, "fresh": False,
        "market_state": None, "note": "test: us_ext disabled"})


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
    _no_us_ext(monkeypatch)
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
    _no_us_ext(monkeypatch)
    factors, diag = fg.sector_keep_factors("nxt", ["AAA"])
    assert diag["gated"] is True and factors["AAA"] == 1.0  # 상승이면 감액 없음


# ── US 장 마감 후(프리/애프터) 확장 축 ──

def test_min_opt():
    assert fg._min_opt(None, None) is None
    assert fg._min_opt(-0.5, None) == -0.5
    assert fg._min_opt(0.3, -1.2) == -1.2      # 가장 약세를 택함


def test_sector_keep_us_ext_semis_only_tech():
    # 반도체 확장 하락은 tech 만 깎고 방어주는 안 깎는다(semis 민감도 tech=1, else 0)
    us = {"semis_pct": -2.0, "korea_pct": None}
    tech = fg._sector_keep("전기/전자", 0.5, 0.5, _SD, us)
    defensive = fg._sector_keep("통신", 0.5, 0.5, _SD, us)
    assert tech < 1.0
    assert defensive == 1.0


def test_sector_keep_us_ext_korea_all_sectors():
    # 한국(EWY) 확장 하락은 전 섹터에 idx 민감도로 작용(방어주도 조금은 깎임)
    us = {"semis_pct": None, "korea_pct": -2.0}
    defensive = fg._sector_keep("통신", 0.5, 0.5, _SD, us)
    assert defensive < 1.0


def test_sector_keep_us_ext_reduce_only_and_none():
    # us_ext=None(KRX/미신선)이면 기존과 동일, 상승 확장은 감액 0, 항상 reduce-only
    base = fg._sector_keep("전기/전자", -0.5, 0.3, _SD)
    assert fg._sector_keep("전기/전자", -0.5, 0.3, _SD, None) == base
    up = {"semis_pct": 1.0, "korea_pct": 0.5}
    assert fg._sector_keep("전기/전자", 0.5, 0.5, _SD, up) == 1.0
    dn = {"semis_pct": -2.0, "korea_pct": -2.0}
    assert fg._sector_keep("전기/전자", 0.5, 0.5, _SD, dn) <= 1.0


def test_keep_factors_krx_skips_us_ext(monkeypatch):
    # KRX 는 미국장 다크 → US 확장 축 미개입(fetch 자체 안 함), diag.us_ext.applied=False
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"krx", "nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, 0.5, 0.5, label="주간선물"))
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {"AAA": "전기/전자"})
    called = {"n": 0}
    monkeypatch.setattr(fg, "_us_ext_signals", lambda: called.__setitem__("n", called["n"] + 1) or {})
    factors, diag = fg.sector_keep_factors("krx", ["AAA"])
    assert called["n"] == 0                       # KRX 에선 US 확장 조회 안 함
    assert diag["us_ext"]["applied"] is False
    assert factors["AAA"] == 1.0


def test_keep_factors_nxt_applies_us_ext(monkeypatch):
    # NXT + 신선 프리마켓 + 반도체 확장 급락 → tech 종목 추가 감액, diag 기록
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, 0.5, 0.5))  # 선물은 보합
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {"AAA": "전기/전자"})
    monkeypatch.setattr(fg, "_us_ext_signals", lambda: {
        "semis_pct": -2.5, "korea_pct": -1.0, "fresh": True,
        "market_state": "PRE", "note": "ok"})
    factors, diag = fg.sector_keep_factors("nxt", ["AAA"])
    assert diag["us_ext"]["applied"] is True and diag["us_ext"]["market_state"] == "PRE"
    assert factors["AAA"] < 1.0                   # 선물 보합이어도 US 확장 하락으로 감액


def test_keep_factors_nxt_us_ext_stale_not_applied(monkeypatch):
    # NXT 라도 미국장 폐장(POST/CLOSED)=stale 이면 US 축 미개입(선물 축은 정상)
    monkeypatch.setattr(fg, "FUTURES_GATE_VENUES", {"nxt"})
    monkeypatch.setattr(fg, "_futures_state", lambda venue: _state(True, 0.5, 0.5))
    monkeypatch.setattr(fg, "_sectors_for", lambda codes: {"AAA": "전기/전자"})
    monkeypatch.setattr(fg, "_us_ext_signals", lambda: {
        "semis_pct": -2.5, "korea_pct": -1.0, "fresh": False,
        "market_state": "POSTPOST", "note": "ok"})
    factors, diag = fg.sector_keep_factors("nxt", ["AAA"])
    assert diag["us_ext"]["applied"] is False
    assert factors["AAA"] == 1.0                  # 선물 보합 + US stale → 감액 없음
