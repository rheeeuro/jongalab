"""엣지 연구용 피처 파생 — 순수 함수(DB·네트워크 무의존).

closing_bet 이 선정 시점(13~15시)에 이미 수집한 응답(시간봉·수급 이력·일봉)에서
daily_stock_report 의 F5 수급 구조형 피처 스칼라를 굽는다. 관측·기록 전용(점수 무영향).
결측·형식 이상은 전부 None 반환 — edge_predicate 가 NULL 을 매칭 실패로 처리하는
보수적 계약과 맞물린다. tests/test_edge_features.py 가 계약을 고정한다.
"""
import math


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


# ── 바이오/제약 분류 (veto_bio rule 용, 2026-07-10 HLB 하한가 사건 대응) ──
# 키움 업종명(upName)은 코스피 의약품·일부만 '제약'으로 주고, 코스닥 바이오벤처 상당수를
# '일반서비스'로 뭉뚱그린다(알테오젠·디앤디파마텍 실측). 업종명 + 사명 키워드 + 알려진 예외
# 코드의 3단 판별로 커버리지를 메운다. 오탐(비바이오→바이오)의 비용은 매수 1건 스킵이라
# 작으므로 재현율(신약주를 놓치지 않기)을 우선한다.
_BIO_SECTORS = frozenset({"제약"})
_BIO_NAME_KEYWORDS = (
    "바이오", "제약", "약품", "파마", "테라퓨틱스", "세라퓨틱스", "생명과학", "메디",
)
_BIO_NAME_SUFFIXES = ("팜",)  # 에스티팜 등. 접두는 오탐(팜스토리 등)이라 접미만 본다.
# 업종명·키워드 둘 다 놓치는 알려진 신약개발주 — 발견되는 대로 여기에 추가한다.
_BIO_CODES = frozenset({
    "196170",  # 알테오젠
    "039200",  # 오스코텍
    "087010",  # 펩트론
    "310210",  # 보로노이
})


def is_bio(code: str | None, name: str | None, sector: str | None) -> int:
    """바이오/제약(임상·허가 등 오버나이트 바이너리 이벤트 리스크) 종목이면 1, 아니면 0.

    종가베팅은 오버나이트 보유 전략인데 하한가에선 손절이 물리적으로 불가하므로,
    이벤트 밀도가 높은 바이오를 제외하는 veto_bio 계열 rule(전면/코스닥만)이 이 컬럼을 참조한다.
    """
    base = (code or "").split("_")[0].split(".")[0]
    if base in _BIO_CODES:
        return 1
    if (sector or "").strip() in _BIO_SECTORS:
        return 1
    nm = (name or "").strip()
    if any(k in nm for k in _BIO_NAME_KEYWORDS):
        return 1
    if nm.endswith(_BIO_NAME_SUFFIXES):
        return 1
    return 0


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


# ── 차트 구조 피처 (전고점·라운드피겨, 2026-07-19) ──

def dist_prior_high_pct(
    daily_highs: list[tuple[str, int]], today: str, current_price: int,
    lookback: int = 250, min_history: int = 20,
) -> float | None:
    """직전 lookback 거래일 전고점(고가 기준, **당일 제외**) 대비 현재가 부호 있는 거리(%).

    daily_highs: [(dt "YYYYMMDD", 고가), ...] 최신순(일봉 응답 순서 그대로).
    음수=전고점 아래(매물벽까지 남은 거리), 양수=전고점 돌파. 당일 봉을 포함하면 급등주는
    항상 자기 자신이 전고점이 되어 매물벽 정보가 사라지므로 반드시 제외한다.
    직전 이력이 min_history 미만(신규상장 등)이면 전고점이 노이즈라 None.
    """
    if not daily_highs or not current_price or current_price <= 0:
        return None
    prior = [h for dt, h in daily_highs if dt != today and h > 0][:lookback]
    if len(prior) < min_history:
        return None
    prior_high = max(prior)
    return round((current_price - prior_high) / prior_high * 100, 2)


def ma5_reclaim(
    daily_ohlc: list[tuple[str, int, int]], today: str, current_price: int,
) -> int | None:
    """5일선 재탈환 패턴 — 전일 5일선 아래 → 당일 5일선 위로 올라선 양봉.

    daily_ohlc: [(dt "YYYYMMDD", 시가, 종가), ...] 최신순(일봉 응답 순서 그대로, 당일 포함).
    당일 종가 자리는 선정 시점 현재가(current_price)를 쓴다. 모두 충족 시 1:
      ① 전일 종가 < 전일 MA5(전일까지 5봉 평균)
      ② 당일 양봉(현재가>당일 시가)  ③ 현재가 > 당일 MA5(현재가 포함 5봉 평균)
    (전일 음봉 조건은 등록 당일(2026-07-19, 표본 축적 전) 사용자 정정으로 제거 —
    이탈 '봉 색'이 아니라 이탈 '위치'가 가설의 본질.)
    첫 봉이 당일이 아니거나(장 전·데이터 지연) 이력 6봉 미만·가격 결측이면 None.
    """
    if not current_price or current_price <= 0:
        return None
    if not daily_ohlc or daily_ohlc[0][0] != today or len(daily_ohlc) < 6:
        return None
    today_open = daily_ohlc[0][1]
    prev_close = daily_ohlc[1][2]
    prior_closes = [c for _, _, c in daily_ohlc[1:6]]  # 전일까지 5봉
    if today_open <= 0 or any(c <= 0 for c in prior_closes):
        return None
    prev_ma5 = sum(prior_closes) / 5
    today_ma5 = (current_price + sum(prior_closes[:4])) / 5
    return int(
        prev_close < prev_ma5               # ① 전일 5일선 아래
        and current_price > today_open      # ② 당일 양봉
        and current_price > today_ma5       # ③ 당일 5일선 재탈환
    )


# ── 외인 서지 후 경과 피처 (수급 눌림/지속 축, 2026-07-19) ──

# 외인 '대량' 순매수 기준(원). trading_engine._normalize_supply_amount 의 100억 구간 경계와
# 같은 스케일 — PDF 통설 사례(외인 150만주≈105억)와도 부합. 임계 변경은 새 컬럼·rule
# 재등록으로만 한다(사전 등록 원칙).
FRGN_SURGE_THRESHOLD_WON = 10_000_000_000


def days_since_frgn_surge(
    supply_history: list, today: str,
    threshold_won: int = FRGN_SURGE_THRESHOLD_WON,
) -> int | None:
    """직전 거래일 중 외인 대량 순매수(>= threshold_won) 서지가 있었던 가장 가까운 날의
    경과 거래일 수(1=직전 거래일, 최대 4 — ka10059 5일 이력의 당일 제외분).

    supply_history: analyze_supply_demand 형식(최신→과거, 당일 잠정치 포함 가능,
    [{"date": "YYYY-MM-DD", "frgn_net_buy": int(원), ...}]). today 는 "YYYY-MM-DD".
    당일 서지는 세지 않는다 — 눌림/지속 가설의 축은 '유입 후 다음 날들'이고, 당일 유입은
    frgn_net_buy 컬럼이 이미 본다. 이력 없음/서지 없음 → None(predicate 매칭 실패).
    """
    if not supply_history:
        return None
    prior = [h for h in supply_history if h.get("date") != today]
    for i, h in enumerate(prior, start=1):
        if (h.get("frgn_net_buy") or 0) >= threshold_won:
            return i
    return None


def red_candle(
    daily_ohlc: list[tuple[str, int, int]], today: str, current_price: int,
) -> int | None:
    """당일 음봉 여부(현재가 < 당일 시가) — 1=음봉, 0=양봉/보합.

    daily_ohlc: ma5_reclaim 과 같은 형식([(dt "YYYYMMDD", 시가, 종가), ...] 최신순, 당일 포함).
    당일 종가 자리는 선정 시점 현재가를 쓴다. 음전(change_pct<0)과 다른 정보 —
    갭업 후 밀린 날은 상승 마감이어도 음봉이다. 첫 봉이 당일이 아니거나 시가 결측이면 None.
    """
    if not current_price or current_price <= 0:
        return None
    if not daily_ohlc or daily_ohlc[0][0] != today:
        return None
    today_open = daily_ohlc[0][1]
    if today_open <= 0:
        return None
    return int(current_price < today_open)


def red_candle_streak(
    daily_ohlc: list[tuple[str, int, int]], today: str, current_price: int,
) -> int | None:
    """당일 포함 연속 음봉 수(당일이 음봉이 아니면 0) — "수급 1음봉/2음봉" 구분용.

    daily_ohlc: red_candle 과 같은 형식([(dt "YYYYMMDD", 시가, 종가), ...] 최신순, 당일 포함).
    당일은 현재가<시가, 이전 봉들은 종가<시가로 거슬러 세고 양봉/보합에서 멈춘다.
    이력 길이(closing_bet 은 6봉)만큼만 세므로 상한은 데이터 길이. 결측 가드는 red_candle 동일.
    """
    if not current_price or current_price <= 0:
        return None
    if not daily_ohlc or daily_ohlc[0][0] != today:
        return None
    today_open = daily_ohlc[0][1]
    if today_open <= 0:
        return None
    if current_price >= today_open:
        return 0
    streak = 1
    for _, o, c in daily_ohlc[1:]:
        if o > 0 and c > 0 and c < o:
            streak += 1
        else:
            break
    return streak


def round_dist_pct(price: int | None) -> float | None:
    """가장 가까운 라운드피겨(1·2·5 × 10^k 원) 대비 부호 있는 거리(%).

    라운드피겨 = 호가창 심리 앵커(예: 5,000 / 10,000 / 20,000 / 50,000 / 100,000원).
    음수=직하단(위에 지정가 매도벽), 양수=돌파 직후. 라운드피겨에서 먼 가격은 절대값이
    커져 밴드 predicate([-2, 0] 등)에 자연히 안 걸린다 — 그 자체가 정보다.
    """
    if not price or price <= 0:
        return None
    scale = 10 ** math.floor(math.log10(price))
    levels = [
        m * base
        for base in (scale // 10, scale, scale * 10) if base > 0
        for m in (1, 2, 5)
    ]
    level = min(levels, key=lambda lv: abs(price - lv))
    return round((price - level) / level * 100, 2)
