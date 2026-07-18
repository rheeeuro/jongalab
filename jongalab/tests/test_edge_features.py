"""core/edge_features.py 계약 고정 — 순수 파생 함수(DB·네트워크 무의존).

결측·형식 이상 → None(edge_predicate 의 'NULL=매칭 실패' 보수 계약과 맞물림)을 중심으로 고정한다.
"""
import pytest

from core.edge_features import (
    afternoon_ret, days_since_frgn_surge, dist_prior_high_pct, is_bio, ma5_reclaim,
    prog_buy_days, red_candle, red_candle_streak, round_dist_pct, vol_ratio,
)

TODAY = "2026-07-03"


# ── afternoon_ret ──

def _bar(time, open_=10000):
    return {"time": time, "open": open_, "high": 0, "low": 0, "close": 0, "volume": 0}


def test_afternoon_ret_basic():
    candles = [_bar(f"{TODAY}T09:00"), _bar(f"{TODAY}T13:00", open_=10000)]
    assert afternoon_ret(candles, 10300, TODAY) == 3.0


def test_afternoon_ret_negative():
    candles = [_bar(f"{TODAY}T13:00", open_=20000)]
    assert afternoon_ret(candles, 19600, TODAY) == -2.0


def test_afternoon_ret_no_13h_bar_returns_none():
    # 오전 실행(13시 봉 미생성) 또는 전일 13시 봉만 있는 경우
    candles = [_bar(f"{TODAY}T09:00"), _bar("2026-07-02T13:00")]
    assert afternoon_ret(candles, 10000, TODAY) is None


@pytest.mark.parametrize("candles,price", [
    ([], 10000),                                # 캔들 없음
    ([_bar(f"{TODAY}T13:00")], 0),              # 현재가 0
    ([_bar(f"{TODAY}T13:00", open_=0)], 10000), # 13시 봉 시가 0(결측)
])
def test_afternoon_ret_missing_returns_none(candles, price):
    assert afternoon_ret(candles, price, TODAY) is None


# ── prog_buy_days ──

def _hist(*prog_amounts):
    return [{"prog_net_buy": a} for a in prog_amounts]


def test_prog_buy_days_counts_positive_only():
    assert prog_buy_days(_hist(100, -50, 0, 200, 300)) == 3


def test_prog_buy_days_none_value_treated_as_zero():
    assert prog_buy_days(_hist(None, 100)) == 1


def test_prog_buy_days_empty_history_returns_none():
    assert prog_buy_days([]) is None


# ── vol_ratio ──

TODAY_YMD = "20260703"


def _vols(today_vol, *prior):
    """최신순 (dt, 거래량) — 일봉 응답 순서."""
    rows = [(TODAY_YMD, today_vol)]
    for i, v in enumerate(prior, 1):
        rows.append((f"2026060{i:02d}"[:8], v))
    return rows


def test_vol_ratio_basic():
    # 직전 5일 평균 100 → 오늘 500 = 5.0배
    assert vol_ratio(_vols(500, 100, 100, 100, 100, 100), TODAY_YMD) == 5.0


def test_vol_ratio_window_caps_prior_days():
    rows = _vols(200, *([100] * 30))
    assert vol_ratio(rows, TODAY_YMD, window=20) == 2.0


def test_vol_ratio_stale_first_candle_returns_none():
    # 첫 캔들이 오늘이 아니면(장 전 실행·데이터 지연) None
    rows = [("20260702", 500), ("20260701", 100)]
    assert vol_ratio(rows, TODAY_YMD) is None


def test_vol_ratio_insufficient_prior_returns_none():
    assert vol_ratio(_vols(500, 100, 100), TODAY_YMD) is None


def test_vol_ratio_zero_today_returns_none():
    assert vol_ratio(_vols(0, 100, 100, 100, 100, 100), TODAY_YMD) is None


# ── is_bio (veto_bio 용 바이오/제약 분류, 2026-07-10) ──

def test_is_bio_by_sector():
    # 키움 업종명 '제약' — HLB(코스닥)·셀트리온(코스피 의약품) 실측 케이스
    assert is_bio("028300", "HLB", "제약") == 1
    assert is_bio("068270", "셀트리온", "제약") == 1


def test_is_bio_by_name_keyword():
    # 코스닥 바이오벤처는 업종명이 '일반서비스'로 뭉뚱그려진다(실측) — 사명 키워드로 보완
    assert is_bio("141080", "리가켐바이오", "일반서비스") == 1
    assert is_bio("347850", "디앤디파마텍", "일반서비스") == 1
    assert is_bio("207940", "삼성바이오로직스", "기타") == 1
    assert is_bio("237690", "에스티팜", "일반서비스") == 1      # 접미 '팜'


def test_is_bio_by_known_code():
    # 업종명·키워드 둘 다 놓치는 알려진 신약개발주 — 코드 목록으로 보정
    assert is_bio("196170", "알테오젠", "일반서비스") == 1
    assert is_bio("196170_NX", "알테오젠", None) == 1           # NX 접미 정규화


def test_is_bio_negative():
    assert is_bio("005930", "삼성전자", "전기/전자") == 0
    assert is_bio("105560", "KB금융", "금융") == 0
    assert is_bio("041830", "인바디", "의료/정밀기기") == 0     # 의료기기는 veto 대상 아님
    assert is_bio(None, None, None) == 0


# ── dist_prior_high_pct (전고점 거리, 2026-07-19) ──

def _highs(today_high, *prior):
    """[(dt, 고가)] 최신순 — 오늘 봉 + 직전 봉들(직전은 최소 이력 20일을 채워 패딩)."""
    rows = [(TODAY_YMD, today_high)]
    prior = list(prior) + [5000] * max(0, 20 - len(prior))
    rows += [(f"2026060{i % 10}", h) for i, h in enumerate(prior)]
    return rows


def test_dist_prior_high_below_wall():
    # 직전 전고점 10,000 vs 현재가 9,500 → 매물벽 -5% 아래
    assert dist_prior_high_pct(_highs(9600, 10000, 8000), TODAY_YMD, 9500) == -5.0


def test_dist_prior_high_breakout_positive():
    assert dist_prior_high_pct(_highs(10600, 10000, 9000), TODAY_YMD, 10500) == 5.0


def test_dist_prior_high_excludes_today():
    # 당일 고가 12,000 이 최고여도 전고점은 직전 봉 기준(10,000) — 당일 포함 시 급등주는
    # 항상 자기 자신이 전고점이 되어 매물벽 정보가 사라진다
    assert dist_prior_high_pct(_highs(12000, 10000, 9500), TODAY_YMD, 11000) == 10.0


def test_dist_prior_high_short_history_returns_none():
    # 직전 이력 20일 미만(신규상장) → 전고점이 노이즈라 None
    rows = [(TODAY_YMD, 10000)] + [("20260601", 9000)] * 5
    assert dist_prior_high_pct(rows, TODAY_YMD, 9500) is None


@pytest.mark.parametrize("rows,price", [
    ([], 10000),                       # 캔들 없음
    ([("20260601", 10000)] * 30, 0),   # 현재가 0
])
def test_dist_prior_high_missing_returns_none(rows, price):
    assert dist_prior_high_pct(rows, TODAY_YMD, price) is None


# ── ma5_reclaim (5일선 재탈환, 2026-07-19 — 전일 음봉 조건은 당일 사용자 정정으로 제거) ──
# 봉: (dt, 시가, 종가) 최신순. 전일까지 5봉 평균 = 전일 MA5.

def _ohlc(today_open, *prev_bars):
    """당일 봉(시가만, 종가는 current_price 인자) + 전일 이후 봉들."""
    rows = [(TODAY_YMD, today_open, 0)]
    rows += [(f"2026061{i}", o, c) for i, (o, c) in enumerate(prev_bars)]
    return rows


# 전일 종가 9800 < 전일 MA5=(9800+10000*4)/5=9960 (5일선 아래).
PREV_BELOW = [(10200, 9800), (9900, 10000), (10100, 10000), (9900, 10000), (10100, 10000)]


def test_ma5_reclaim_full_pattern():
    # 당일 양봉(9900→10500), 당일 MA5=(10500+9800+10000*3)/5=10060 < 10500(재탈환)
    assert ma5_reclaim(_ohlc(9900, *PREV_BELOW), TODAY_YMD, 10500) == 1


def test_ma5_reclaim_prev_candle_color_irrelevant():
    # 전일이 양봉(9700→9800)이어도 5일선 아래였으면 충족 — 이탈 '위치'만 보고 봉 색은 안 본다
    bars = [(9700, 9800)] + PREV_BELOW[1:]
    assert ma5_reclaim(_ohlc(9900, *bars), TODAY_YMD, 10500) == 1


def test_ma5_reclaim_prev_above_ma5_fails():
    # 전일 종가가 5일선 위(10100 > 폭락 포함 MA5=9620)면 '이탈 후 재탈환'이 아님
    bars = [(10300, 10100), (9900, 10000), (10100, 10000), (9900, 10000), (10100, 8000)]
    assert ma5_reclaim(_ohlc(10000, *bars), TODAY_YMD, 10500) == 0


def test_ma5_reclaim_today_bearish_fails():
    # 당일 음봉(시가 10600 > 현재가 10500)이면 불충족 — 5일선 위여도 '뚫는 양봉'이 아님
    assert ma5_reclaim(_ohlc(10600, *PREV_BELOW), TODAY_YMD, 10500) == 0


def test_ma5_reclaim_below_ma5_today_fails():
    # 당일 양봉이어도 현재가가 5일선(9960 부근) 아래면 불충족
    assert ma5_reclaim(_ohlc(9700, *PREV_BELOW), TODAY_YMD, 9800) == 0


@pytest.mark.parametrize("rows,price", [
    ([], 10000),                                   # 캔들 없음
    (_ohlc(9900, *PREV_BELOW), 0),                 # 현재가 0
    (_ohlc(9900, *PREV_BELOW[:3]), 10500),         # 이력 6봉 미만
    ([("20260601", 9900, 9800)] * 6, 10500),       # 첫 봉이 당일 아님(데이터 지연)
])
def test_ma5_reclaim_missing_returns_none(rows, price):
    assert ma5_reclaim(rows, TODAY_YMD, price) is None


# ── round_dist_pct (라운드피겨 거리, 2026-07-19) ──

@pytest.mark.parametrize("price,expected", [
    (9870, -1.3),     # 10,000원 직하단
    (10200, 2.0),     # 10,000원 돌파 직후
    (49000, -2.0),    # 50,000원 직하단
    (19800, -1.0),    # 20,000원 직하단
    (987, -1.3),      # 1,000원 직하단 (저가주 스케일)
    (5000, 0.0),      # 정확히 레벨 위
    (12340, 23.4),    # 어느 레벨에서도 멂 — 밴드 predicate 에 안 걸리는 것이 정상
])
def test_round_dist_pct(price, expected):
    assert round_dist_pct(price) == expected


@pytest.mark.parametrize("price", [0, None, -100])
def test_round_dist_pct_invalid_returns_none(price):
    assert round_dist_pct(price) is None


# ── days_since_frgn_surge (외인 서지 후 경과, 2026-07-19) ──
# supply_history: 최신→과거, 당일 잠정치 포함. 기본 임계 100억.

EOK = 100_000_000


_PRIOR_DATES = ("2026-07-02", "2026-07-01", "2026-06-30", "2026-06-29")


def _supply(*frgn_eoks):
    """당일(TODAY) + 직전 일들의 수급 이력. frgn_eoks[0]=당일, 이후 과거 순."""
    rows = [{"date": TODAY, "frgn_net_buy": frgn_eoks[0] * EOK}]
    rows += [
        {"date": d, "frgn_net_buy": a * EOK}
        for d, a in zip(_PRIOR_DATES, frgn_eoks[1:])
    ]
    return rows


def test_days_since_frgn_surge_yesterday():
    assert days_since_frgn_surge(_supply(10, 150, 5, 5, 5), TODAY) == 1


def test_days_since_frgn_surge_two_days_ago():
    assert days_since_frgn_surge(_supply(10, 5, 150, 5, 5), TODAY) == 2


def test_days_since_frgn_surge_nearest_wins():
    # 어제·그제 모두 서지면 가장 가까운 날(1)
    assert days_since_frgn_surge(_supply(10, 150, 300, 5, 5), TODAY) == 1


def test_days_since_frgn_surge_today_not_counted():
    # 당일 대량 유입은 세지 않는다 — 축은 '유입 후 다음 날들'
    assert days_since_frgn_surge(_supply(500, 5, 5, 5, 5), TODAY) is None


def test_days_since_frgn_surge_below_threshold_returns_none():
    assert days_since_frgn_surge(_supply(10, 99, 99, 99, 99), TODAY) is None


def test_days_since_frgn_surge_without_today_row():
    # 오전 실행 등으로 이력에 당일 행이 없어도 직전일 인덱스는 동일
    rows = _supply(500, 150, 5, 5, 5)[1:]
    assert days_since_frgn_surge(rows, TODAY) == 1


def test_days_since_frgn_surge_empty_returns_none():
    assert days_since_frgn_surge([], TODAY) is None


# ── red_candle (당일 음봉 여부, 2026-07-19) ──
# ma5_reclaim 과 같은 daily_ohlc 형식 재사용 — (dt, 시가, 종가) 최신순.

TODAY_YMD_RC = "20260703"


def _rc_ohlc(today_open):
    return [(TODAY_YMD_RC, today_open, 0), ("20260702", 10000, 10000)]


def test_red_candle_bearish():
    assert red_candle(_rc_ohlc(10600), TODAY_YMD_RC, 10500) == 1


def test_red_candle_bullish():
    assert red_candle(_rc_ohlc(10400), TODAY_YMD_RC, 10500) == 0


def test_red_candle_flat_is_not_red():
    assert red_candle(_rc_ohlc(10500), TODAY_YMD_RC, 10500) == 0


def test_red_candle_gap_up_fade_still_red():
    # 갭업 후 밀림: 상승 마감(음전 아님)이어도 시가 아래면 음봉 — change_pct 와 다른 정보
    assert red_candle([(TODAY_YMD_RC, 11000, 0), ("20260702", 9000, 10000)],
                      TODAY_YMD_RC, 10500) == 1


@pytest.mark.parametrize("rows,price", [
    ([], 10500),                                    # 캔들 없음
    (_rc_ohlc(10600), 0),                           # 현재가 0
    (_rc_ohlc(0), 10500),                           # 당일 시가 결측
    ([("20260702", 10000, 10000)], 10500),          # 첫 봉이 당일 아님(데이터 지연)
])
def test_red_candle_missing_returns_none(rows, price):
    assert red_candle(rows, TODAY_YMD_RC, price) is None


# ── red_candle_streak (당일 포함 연속 음봉 수, 2026-07-19 — 수급 1음봉/2음봉 구분) ──

RED = (10500, 10000)    # 음봉(시가 10500 → 종가 10000)
GREEN = (10000, 10500)  # 양봉


def _streak_ohlc(today_open, *prev_bars):
    rows = [(TODAY_YMD_RC, today_open, 0)]
    rows += [(f"202606{28 - i:02d}", o, c) for i, (o, c) in enumerate(prev_bars)]
    return rows


def test_streak_today_green_is_zero():
    assert red_candle_streak(_streak_ohlc(10400, RED, RED), TODAY_YMD_RC, 10500) == 0


def test_streak_one_first_red_after_green():
    # 당일 음봉 + 전일 양봉 → 1음봉
    assert red_candle_streak(_streak_ohlc(10600, GREEN, RED), TODAY_YMD_RC, 10500) == 1


def test_streak_two_consecutive_red():
    # 당일·전일 연속 음봉 + 그 전 양봉 → 2음봉
    assert red_candle_streak(_streak_ohlc(10600, RED, GREEN), TODAY_YMD_RC, 10500) == 2


def test_streak_three():
    assert red_candle_streak(_streak_ohlc(10600, RED, RED, GREEN), TODAY_YMD_RC, 10500) == 3


def test_streak_stops_at_flat_candle():
    # 보합봉(시가=종가)은 음봉이 아니므로 스트릭 중단
    assert red_candle_streak(_streak_ohlc(10600, (10000, 10000), RED), TODAY_YMD_RC, 10500) == 1


def test_streak_stops_at_missing_prior_price():
    # 이전 봉 가격 결측(0)은 보수적으로 중단 — 과대 스트릭 방지
    assert red_candle_streak(_streak_ohlc(10600, (0, 10000), RED), TODAY_YMD_RC, 10500) == 1


@pytest.mark.parametrize("rows,price", [
    ([], 10500),                                    # 캔들 없음
    (_streak_ohlc(10600, RED), 0),                  # 현재가 0
    (_streak_ohlc(0, RED), 10500),                  # 당일 시가 결측
    ([("20260702", 10500, 10000)], 10500),          # 첫 봉이 당일 아님
])
def test_streak_missing_returns_none(rows, price):
    assert red_candle_streak(rows, TODAY_YMD_RC, price) is None
