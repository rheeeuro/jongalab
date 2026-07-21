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


# ── 재무 스냅샷 (2026-07-22) — ka10001 응답 재사용, 추가 API 콜 없음 ──
# closing_bet 이 선정 시점(13~15시)에 후보마다 이미 호출하는 주식기본정보(ka10001) 응답에
# per/pbr/ev/roe/eps/bps/매출·영업이익·순이익이 실려온다(현재는 시가총액·외인소진율만 사용).
# 분기 저속 데이터라 매일 같은 값이 중복 저장될 수 있으나 연구용으로 무해하다. 점수 무영향.
# 부채비율은 ka10001 에 없어 제외한다(별도 재무제표 TR 필요).


def _parse_fin_num(s) -> float | None:
    """ka10001 재무 문자열 → 숫자. 부호 접두(+/-)·천단위 콤마 처리, 공란/파싱불가는 None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    if t in ("", "-", "+"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _fin_int(s) -> int | None:
    """정수 재무 필드(원·억원 단위) 파싱 — _parse_fin_num 후 int 절사."""
    v = _parse_fin_num(s)
    return int(v) if v is not None else None


def financials(info: dict) -> dict:
    """ka10001(주식기본정보) 응답에서 재무 스냅샷 피처를 추출한다(관측·연구용, 점수 무영향).

    반환 키(전부 결측 시 None):
      fin_per / fin_pbr / fin_ev   — 밸류에이션(배)
      fin_roe                      — 자기자본이익률(%)
      fin_eps / fin_bps            — 주당순이익·주당순자산(원)
      fin_sales / fin_op_profit / fin_net_income — 매출액·영업이익·당기순이익(억원)
    """
    if not info:
        return {}
    return {
        "fin_per": _parse_fin_num(info.get("per")),
        "fin_pbr": _parse_fin_num(info.get("pbr")),
        "fin_ev": _parse_fin_num(info.get("ev")),
        "fin_roe": _parse_fin_num(info.get("roe")),
        "fin_eps": _fin_int(info.get("eps")),
        "fin_bps": _fin_int(info.get("bps")),
        "fin_sales": _fin_int(info.get("sale_amt")),
        "fin_op_profit": _fin_int(info.get("bus_pro")),
        "fin_net_income": _fin_int(info.get("cup_nga")),
    }


# ── 호가 미시구조 스냅샷 (2026-07-22) — ka10004 주식호가요청 파생 ──
# 선정 시점(closing_bet 13~15시) 호가창의 잔량 불균형·스프레드. 오버나이트 갭 방향의
# 단기 미시구조 신호. 연속장 밖(장 종료·개장 전)엔 잔량이 전부 0 으로 와서 분모 0 가드로
# 자연스럽게 None → repository PRESERVE_ON_NULL 이 마지막 세션 스냅샷을 보존한다.
# 실제 매수는 종가라 ~15시 스냅샷은 근사치임을 라벨 해석 시 감안.


def _ob_num(s) -> float | None:
    """ka10004 호가 문자열 → 크기(부호·콤마 제거 후 절대값). 공란/파싱불가는 None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    if t in ("", "-", "--", "+"):
        return None
    try:
        return abs(float(t))
    except ValueError:
        return None


def order_book_features(ob: dict, current_price: int | None) -> dict:
    """ka10004(주식호가) 응답 → 호가 미시구조 파생 스칼라(관측·연구용, 점수 무영향).

    반환 키(분모 0/결측 시 None):
      ob_imbalance     — 총매수잔량 ÷ 총매도잔량(>1 이면 매수 우위)
      ob_fpr_imbalance — 매수최우선잔량 ÷ 매도최우선잔량(1호가 압력)
      ob_spread_pct    — (매도최우선호가 − 매수최우선호가) ÷ 현재가 × 100(체결비용·유동성)
    """
    if not ob:
        return {}
    tot_sel = _ob_num(ob.get("tot_sel_req"))
    tot_buy = _ob_num(ob.get("tot_buy_req"))
    sel_fpr_req = _ob_num(ob.get("sel_fpr_req"))
    buy_fpr_req = _ob_num(ob.get("buy_fpr_req"))
    sel_fpr_bid = _ob_num(ob.get("sel_fpr_bid"))
    buy_fpr_bid = _ob_num(ob.get("buy_fpr_bid"))

    imbalance = (
        round(tot_buy / tot_sel, 4)
        if tot_sel and tot_buy is not None else None
    )
    fpr_imbalance = (
        round(buy_fpr_req / sel_fpr_req, 4)
        if sel_fpr_req and buy_fpr_req is not None else None
    )
    spread_pct = (
        round((sel_fpr_bid - buy_fpr_bid) / current_price * 100, 3)
        if current_price and current_price > 0 and sel_fpr_bid and buy_fpr_bid else None
    )
    return {
        "ob_imbalance": imbalance,
        "ob_fpr_imbalance": fpr_imbalance,
        "ob_spread_pct": spread_pct,
    }


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


# ── 프로그램 장중 오전/오후 분해 (2026-07-19 — "오전 프로그램 매도→오후 매수 전환" 통설) ──

def _parse_prog_amt(s) -> int | None:
    """ka90008 누적 순매수 금액(백만원, 음수는 '--' 이중부호) → 원. 결측/형식 이상은 None."""
    if s is None:
        return None
    s = str(s).strip().replace("--", "-").lstrip("+")
    if not s or s == "-":
        return None
    try:
        return int(s) * 1_000_000
    except ValueError:
        return None


def prog_cum_net(prog_rows: list, min_tm: str = "090000", max_tm: str = "153500") -> int | None:
    """ka90008 최신 행의 당일 프로그램 누적 순매수(원). 스냅샷 캡처용.

    prog_rows: ka90008 응답(stk_tm_prm_trde_trnsn) 그대로 — 최신→과거, tm "HHMMSS",
    prm_netprps_amt 당일 누적(백만원). 최신 행 tm 이 [min_tm, max_tm] 밖이면 None —
    키움이 당일 데이터 없을 때 최근 거래일을 폴백 반환하는 것과 NXT 애프터 틱을 걸러낸다.

    사용처(오전/오후 분해): 틱 시계열은 유동 종목에서 12:00 도달에 50페이지+ 가 필요해
    (2026-07-19 실측, 삼성전자 12:00~14:30 구간만 11,256틱) 페이지 워킹이 비현실적이다.
    대신 30분 주기 closing_bet 의 정오 창 실행이 이 스냅샷(1페이지)을 prog_am_net 으로
    저장하고, 오후 실행이 (현재 스냅샷 − 저장된 정오값)으로 prog_pm_net 을 계산한다.
    """
    if not prog_rows:
        return None
    tm = prog_rows[0].get("tm") or ""
    if not (min_tm <= tm <= max_tm):
        return None
    return _parse_prog_amt(prog_rows[0].get("prm_netprps_amt"))


# ── 매물대(볼륨프로파일) 피처 (2026-07-19 — 일봉 근사, rule 은 레벨 축 판정 후 등록) ──
# dist_prior_high_pct 는 전고점의 '위치'만 본다 — 그 고점이 스파이크로 스친 얇은 고점인지
# 수개월 횡보로 다져진 두터운 벽인지 구분하지 못한다. 아래 둘이 '물량'을 본다.
# 각 일봉의 거래량을 저가~고가 구간에 균등 배분하는 근사(분봉 없이 1콜 재사용).

def overhead_vol_ratio(
    daily_bars: list[tuple[str, int, int, int]], current_price: int,
    lookback: int = 250, min_history: int = 20,
) -> float | None:
    """직전 lookback 거래일(당일 포함) 거래량 중 현재가 '위'에서 거래된 비중(0~1).

    daily_bars: [(dt "YYYYMMDD", 고가, 저가, 거래량), ...] 최신순(일봉 응답 순서 그대로).
    비중이 클수록 현재가 위에 물린 물량(잠재 본전 매도 압력)이 두텁다 — 0에 가까우면
    "머리 위 매물 없음"(신고가 논리)의 정량판. 당일 봉 포함 — 당일 고가 부근 매수자도
    현재가 아래로 밀렸다면 실재하는 매물이다. 이력 min_history 미만·거래량 0이면 None.
    """
    if not current_price or current_price <= 0:
        return None
    bars = [
        (h, l, v) for _, h, l, v in daily_bars[:lookback]
        if h > 0 and l > 0 and h >= l and v > 0
    ]
    if len(bars) < min_history:
        return None
    total = 0.0
    above = 0.0
    for h, l, v in bars:
        total += v
        if l >= current_price:
            above += v
        elif h > current_price:
            above += v * (h - current_price) / (h - l)
    if total <= 0:
        return None
    return round(above / total, 4)


def poc_dist_pct(
    daily_bars: list[tuple[str, int, int, int]], current_price: int,
    lookback: int = 250, min_history: int = 20, bins: int = 40,
) -> float | None:
    """최대 거래 집중 가격대(POC, Point of Control) 대비 현재가 부호 있는 거리(%).

    daily_bars: overhead_vol_ratio 와 같은 형식. lookback 저가~고가 전 범위를 bins 등분해
    각 봉 거래량을 겹치는 구간에 균등 배분한 히스토그램의 최대 구간 중심이 POC.
    양수=매물대 위(하락 시 지지 후보), 음수=아래(상승 시 저항 후보), 0 부근=매물대 한복판.
    이력 min_history 미만이면 None.
    """
    if not current_price or current_price <= 0:
        return None
    bars = [
        (h, l, v) for _, h, l, v in daily_bars[:lookback]
        if h > 0 and l > 0 and h >= l and v > 0
    ]
    if len(bars) < min_history:
        return None
    lo = min(l for _, l, _ in bars)
    hi = max(h for h, _, _ in bars)
    if hi <= lo:
        poc = float(hi)
    else:
        width = (hi - lo) / bins
        hist = [0.0] * bins
        for h, l, v in bars:
            if h == l:
                idx = min(int((h - lo) / width), bins - 1)
                hist[idx] += v
                continue
            density = v / (h - l)
            for i in range(bins):
                b_lo = lo + i * width
                b_hi = b_lo + width
                overlap = min(h, b_hi) - max(l, b_lo)
                if overlap > 0:
                    hist[i] += density * overlap
        best = max(range(bins), key=lambda i: hist[i])
        poc = lo + (best + 0.5) * width
    if poc <= 0:
        return None
    return round((current_price - poc) / poc * 100, 2)


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
