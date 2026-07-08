"""daily_ohlc 라벨 공용 헬퍼 계약 테스트."""
from core.daily_ohlc import (
    build_minute_price_by_time,
    first_price_at_or_after,
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
