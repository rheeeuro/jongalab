"""daily_stock_report 뉴스 라벨 upsert 계약 고정 (순수 로직 — DB 접속 없음).

2026-07-29 실제로 밟은 함정을 고정한다: LLM 라벨 컬럼 중 3개(news_summary/news_sentiment/
news_catalyst)를 캐리포워드 목록과 preserve-on-null 목록에서 빼먹어, **캐시 스킵 실행이
그 3개만 NULL 로 덮었다** — 4축은 살아남아 한 행 안에서 라벨이 어긋났다(방향은 비었는데
지속성 등급은 있는 상태). 라벨은 결과가 나올 때까지 틀린 티가 안 나므로 계약으로 못박는다.
"""
from core.repository.stock_report import (
    _NEWS_LABEL_COLS,
    _PRESERVE_ON_NULL,
    _analysis_row,
)

_MIN_CANDIDATE = {
    "stock_code": "005930", "stock_name": "삼성전자", "sector": "전기/전자",
    "current_price": 70000, "change_pct": 1.0, "trading_value": 1e12, "market_cap": 4e14,
    "inst_net_buy": 0, "frgn_net_buy": 0, "indv_net_buy": 0, "prog_net_buy": 0,
    "supply_days": 1, "ma_aligned": 1, "near_high": 0, "is_leader": 1,
    "score": 80.0, "rank_no": 1,
}


def test_뉴스_라벨_컬럼은_전부_분석컬럼에_있다():
    """_analysis_row 에 없으면 판정 결과가 아예 저장되지 않는다."""
    row = _analysis_row(_MIN_CANDIDATE)
    missing = [c for c in _NEWS_LABEL_COLS if c not in row]
    assert not missing, f"분석 컬럼에 없는 라벨: {missing}"


def test_뉴스_라벨_컬럼은_전부_preserve_on_null_이다():
    """새 헤드라인이 없어 판정을 건너뛴 실행의 NULL 이 그날 라벨을 지우면 안 된다."""
    missing = [c for c in _NEWS_LABEL_COLS if c not in _PRESERVE_ON_NULL]
    assert not missing, f"preserve-on-null 에서 빠진 라벨: {missing}"


def test_라벨_값은_그대로_행에_실린다():
    row = _analysis_row({
        **_MIN_CANDIDATE,
        "news_sentiment": 70, "news_catalyst": "수주계약", "news_durability": "연속",
        "news_next_milestone": 1, "news_amount_locked": 0,
    })
    assert row["news_sentiment"] == 70
    assert row["news_catalyst"] == "수주계약"
    assert row["news_durability"] == "연속"
    assert row["news_next_milestone"] == 1
    assert row["news_amount_locked"] == 0
