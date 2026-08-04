"""수정주가 일봉(ka10081)·분봉(ka10080) 파싱 + 결과 라벨 아티팩트 가드.

outcome_backfill(일봉 라벨 4종·실집행 레그)과 gap_check --label-nxt(08:06 프리마켓 라벨)가 함께 쓴다.
라벨 간 유효성 기준(±SANE_RET_PCT)·차트 파싱이 어긋나면 exit_label 쌍둥이 rule 의
청산창 비교가 조용히 오염되므로, 라벨을 만드는 코드는 반드시 이 모듈만 사용한다.
"""
import logging

from core.kiwoom_client import KiwoomRestClient
from core.trading_engine import AnalysisEngine

logger = logging.getLogger("DailyOhlc")

# 한 세션 오버나이트 등락 상한(%) — KR 일일 등락제한 ±30% 여유.
# 넘으면 분할·데이터 아티팩트로 보고 해당 라벨을 버린다(모든 결과 라벨에 동일 적용).
SANE_RET_PCT = 35.0

# 수정주가 일봉 종가와 그날 **실제 거래 종가**(미조정)의 허용 오차(%).
# 넘으면 리포트일 이후 권리락(무상증자·분할 등)이 있었다는 뜻이다 — 아래 주석 참조.
PRICE_SCALE_TOL_PCT = 2.0


def is_price_scale_shifted(adj_close: int | None, raw_close: int | None) -> bool:
    """수정주가 일봉 종가와 미조정 실거래 종가의 **가격 스케일이 어긋났는가**.

    [왜 필요한가]
    ka10081 수정주가 일봉은 무상증자·분할 권리락을 **과거로 소급 조정**하지만, ka10080 분봉과
    저장된 `krx_close_price`·NXT 프리마켓 시세는 그날 실거래가를 그대로 준다. 그래서 리포트일
    다음 거래일이 권리락일이면 **일봉 라벨(next_*_ret)만 정상**이고, 미조정 가격 양 끝으로
    계산하는 라벨(exec_leg_ret·nxt_open_ret)은 배정비율만큼 손실로 찍힌다.
      2026-08-04 대동기어 실측: 8/3 19:50 분봉 9,594 → 8/4 09:03 분봉 7,510 = **-21.7%**.
      실제로는 그날 +1.76% 오른 종목이고, ±SANE_RET_PCT 가드도 통과해 그대로 저장된다.
    권리락 공시일로는 판정할 수 없다 — 공시일→권리락일 간격이 종목마다 다르다
    (알테오젠 8/4 공시→8/5 권리락 / 대동기어 7/31 공시→8/4 권리락). 그래서 **가격 스케일**을
    직접 비교한다: 조정·미조정 두 값은 권리락이 없으면 같아야 한다(2026-08-03 유니버스
    48행 전건 일치, 오탐 0). 반올림 오차만 PRICE_SCALE_TOL_PCT 로 흘린다.

    둘 중 하나라도 없으면 판정 불가 → False(미개입, 라벨을 버리지 않는다).
    """
    if not adj_close or not raw_close or adj_close <= 0 or raw_close <= 0:
        return False
    return abs(raw_close - adj_close) / adj_close * 100 > PRICE_SCALE_TOL_PCT


def build_ohlc_by_date(api: KiwoomRestClient, code: str) -> dict[str, tuple[int, int, int, int]]:
    """{YYYYMMDD: (시가, 고가, 저가, 종가)} 맵 — 수정주가 일봉 1회 조회(분할 상쇄).

    조회 실패/빈 응답은 {} (호출부가 라벨 스킵으로 처리). code 는 접미사 없는 종목코드.
    """
    try:
        data = api.get_daily_chart(code)
    except Exception as e:
        logger.warning(f"[{code}] 일봉 조회 실패: {e}")
        return {}
    m: dict[str, tuple[int, int, int, int]] = {}
    for c in data.get("stk_dt_pole_chart_qry", []):
        dt = c.get("dt", "")
        op = abs(AnalysisEngine.parse_price(c.get("open_pric", "0")))
        hi = abs(AnalysisEngine.parse_price(c.get("high_pric", "0")))
        lo = abs(AnalysisEngine.parse_price(c.get("low_pric", "0")))
        cl = abs(AnalysisEngine.parse_price(c.get("cur_prc", "0")))
        if len(dt) == 8 and op > 0 and hi > 0 and lo > 0 and cl > 0:
            m[dt] = (op, hi, lo, cl)
    return m


def build_minute_price_by_time(
    api: KiwoomRestClient,
    code: str,
    *,
    nxt: bool = False,
    base_dt: str = "",
    max_pages: int = 2,
) -> dict[str, int]:
    """{YYYYMMDDHHMM: 체결가} 맵 — 1분봉 연속조회.

    code 는 접미사 없는 종목코드. nxt=True 면 `{code}_NX` 로 조회한다.
    조회 실패/빈 응답은 {}. 체결가는 분봉 종가(cur_prc)를 쓴다.
    """
    stk_cd = code if not nxt or code.endswith("_NX") else f"{code}_NX"
    try:
        rows = api.get_minute_chart_pages(
            stk_cd, tic_scope="1", base_dt=base_dt, max_pages=max_pages
        )
    except Exception as e:
        logger.warning(f"[{stk_cd}] 분봉 조회 실패: {e}")
        return {}

    out: dict[str, int] = {}
    for c in rows or []:
        tm = str(c.get("cntr_tm", ""))[:12]
        px = abs(AnalysisEngine.parse_price(c.get("cur_prc", "0")))
        if len(tm) == 12 and px > 0:
            out[tm] = px
    return out


def first_price_at_or_after(
    prices_by_time: dict[str, int],
    target_tm: str,
) -> tuple[str, int] | None:
    """target_tm(YYYYMMDDHHMM) 당일의 target 이후 첫 체결가.

    날짜가 넘어간 다음 체결을 잡으면 19:50 기준가가 08:00 가격으로 오염될 수 있어,
    같은 YYYYMMDD 안에서만 찾는다.
    """
    if len(target_tm) != 12:
        return None
    day = target_tm[:8]
    for tm in sorted(t for t in prices_by_time if t.startswith(day) and t >= target_tm):
        return tm, prices_by_time[tm]
    return None


def first_later_chart_date(ohlc: dict[str, tuple[int, int, int, int]], report_dt: str) -> str | None:
    """일봉 차트에서 report_dt 이후 첫 거래일(YYYYMMDD)."""
    later = sorted(d for d in ohlc if d > report_dt)
    return later[0] if later else None


def ret_pct(base_price: int, exit_price: int) -> float | None:
    """라벨 공통 등락률 계산. ±SANE_RET_PCT 초과는 아티팩트로 버린다."""
    if base_price <= 0 or exit_price <= 0:
        return None
    r = (exit_price - base_price) / base_price * 100
    if abs(r) > SANE_RET_PCT:
        return None
    return round(r, 3)

