"""daily_ohlc 라벨 공용 헬퍼 계약 테스트."""
from core.daily_ohlc import (
    build_minute_price_by_time,
    first_price_at_or_after,
    is_price_scale_shifted,
    ret_pct,
)


class FakeApi:
    def get_minute_chart_pages(self, stk_cd, tic_scope="1", base_dt="", max_pages=2):
        assert stk_cd == "005930_NX"
        assert tic_scope == "1"
        assert base_dt == "20260708"
        assert max_pages == 2
        return [
            {"cntr_tm": "20260707195000", "cur_prc": "71000"},
            {"cntr_tm": "20260708080300", "cur_prc": "71500"},
        ]


def test_build_minute_price_by_time_uses_nxt_suffix_and_minute_key():
    prices = build_minute_price_by_time(FakeApi(), "005930", nxt=True, base_dt="20260708")
    assert prices == {"202607071950": 71000, "202607080803": 71500}


def test_first_price_at_or_after_stays_on_target_day():
    prices = {
        "202607071951": 100,
        "202607080800": 120,
    }
    assert first_price_at_or_after(prices, "202607071950") == ("202607071951", 100)
    assert first_price_at_or_after(prices, "202607071959") is None


def test_ret_pct_applies_sane_guard():
    assert ret_pct(100, 103) == 3.0
    assert ret_pct(100, 140) is None


def test_price_scale_shift_detects_ex_rights():
    """권리락이면 수정 일봉 종가와 실거래 종가의 스케일이 배정비율만큼 벌어진다.

    2026-08-04 대동기어 실측: 8/3 수정 일봉 종가 7,380 vs 실거래 종가 9,594 (무상증자 0.3주).
    이 상태로 분봉 라벨을 만들면 -21.7% 가 손실로 찍히고 ±SANE_RET_PCT 도 통과한다.
    """
    assert is_price_scale_shifted(7380, 9594) is True
    # 정상 종목은 두 값이 같다 (2026-08-03 유니버스 48행 전건 일치)
    assert is_price_scale_shifted(47750, 47750) is False
    # 반올림 오차(≤2%)는 흘린다 — 라벨을 과잉 폐기하지 않는다
    assert is_price_scale_shifted(10000, 10150) is False
    # 판정 불가(값 결측)는 미개입 = 라벨 유지
    assert is_price_scale_shifted(None, 9594) is False
    assert is_price_scale_shifted(7380, None) is False
    assert is_price_scale_shifted(0, 0) is False
