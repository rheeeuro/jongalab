"""엣지 연구용 피처 파생 — 순수 함수(DB·네트워크 무의존).

closing_bet 이 선정 시점(13~15시)에 이미 수집한 응답(시간봉·수급 이력·일봉)에서
daily_stock_report 의 F5 수급 구조형 피처 스칼라를 굽는다. 관측·기록 전용(점수 무영향).
결측·형식 이상은 전부 None 반환 — edge_predicate 가 NULL 을 매칭 실패로 처리하는
보수적 계약과 맞물린다. tests/test_edge_features.py 가 계약을 고정한다.
"""


def afternoon_ret(hourly_candles: list, current_price: int, today: str) -> float | None:
    """당일 13:00 시간봉 시가 → 현재가 등락률(%).

    hourly_candles: fetch_hourly_candles 형식([{"time": "YYYY-MM-DDTHH:MM", "open": int, ...}]).
    시간봉 라벨은 봉 시작 시각(09:00~15:00). 13시 봉이 아직 없으면(오전 실행) None.
    """
    if not hourly_candles or not current_price or current_price <= 0:
        return None
    target = f"{today}T13:00"
    for c in hourly_candles:
        if c.get("time") == target:
            base = c.get("open") or 0
            if base <= 0:
                return None
            return round((current_price - base) / base * 100, 2)
    return None


def prog_buy_days(supply_history: list) -> int | None:
    """최근 5일 수급 이력(supply_history) 중 프로그램 순매수(>0)일 수. 이력 없으면 None."""
    if not supply_history:
        return None
    return sum(1 for d in supply_history if (d.get("prog_net_buy") or 0) > 0)


def vol_ratio(daily_volumes: list[tuple[str, int]], today: str, window: int = 20) -> float | None:
    """당일 거래량 ÷ 직전 window 일 평균 거래량.

    daily_volumes: [(dt "YYYYMMDD", 거래량), ...] 최신순(일봉 응답 순서 그대로).
    첫 원소가 오늘이 아니거나(장 전·데이터 지연) 직전 표본이 5일 미만이면 None.
    """
    if not daily_volumes or daily_volumes[0][0] != today:
        return None
    prior = [v for _, v in daily_volumes[1:window + 1] if v > 0]
    if len(prior) < 5:
        return None
    today_vol = daily_volumes[0][1]
    if today_vol <= 0:
        return None
    return round(today_vol / (sum(prior) / len(prior)), 2)
