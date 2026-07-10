"""core/edge_features.py 계약 고정 — 순수 파생 함수(DB·네트워크 무의존).

결측·형식 이상 → None(edge_predicate 의 'NULL=매칭 실패' 보수 계약과 맞물림)을 중심으로 고정한다.
"""
import pytest

from core.edge_features import afternoon_ret, is_bio, prog_buy_days, vol_ratio

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
