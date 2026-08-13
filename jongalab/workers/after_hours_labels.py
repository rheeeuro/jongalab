"""시간외 반응 + 리스크 라벨 수집 워커 — 당일 유니버스에 관측 라벨 채우기.

엣지 연구용: daily_stock_report 당일 유니버스 전 종목에 다음 라벨을 UPDATE 로 채운다
(점수·선정 무영향, closing_bet 의 upsert 대상이 아니라 재실행에도 보존).

  시간외 반응 (익일 갭 선행지표 — ka10087 스냅샷, 시간외단일가 세션 16~18시 **중**에만 값이
              살아있고 종료 후엔 0으로 리셋되므로 17:50 에 수집한다. 마지막 18:00 체결 1회만 누락)
    ah_price / ah_flu_rt / ah_volume — 시간외단일가 현재가·등락률(전일종가 대비)·누적거래량
    ah_react — 시간외단일가 ÷ 당일 KRX 종가 − 1 (%) (앵커=수정주가 일봉 당일 캔들, 실험실 rule 용)
  리스크 지표 (악재 veto 연구 — 전부 T-1 확정 일별 시계열이라 선정 시점에 알 수 있던 값)
    credit_remn_rt        — 신용융자 잔고율(%) (ka10013)
    short_wght / _5d      — 공매도 매매비중(%) T-1 / 직전 5거래일 평균 (ka10014)
    lend_remn / lend_irds_5d — 대차 잔고주수 T-1 / 직전 5거래일 증감 합 (ka20068)
  체결강도 (진입 강도 팩터 — ka10047, 17:50 수집이라 KRX 마감 후 당일 확정치)
    exec_str / exec_str_5d — 당일 마감 체결강도 / 5일 평균

추가로 시장 분위기: ka10098(시간외 등락률 순위, ETF·ETN 제외)에서 ±3% 이상 급등/급락
종목 수를 market_snapshot(ah_up3_cnt/ah_dn3_cnt)에 굽는다.

[주의]
  - 시간외단일가는 스냅샷 TR 이라 당일 세션 중에만 수집 가능(과거 백필 불가) — 놓친 날은 NULL.
    시간외 체결이 없는 종목(누적거래량 0)도 NULL(0.0 오염 방지).
  - 17:50 이후 closing_bet 재실행(18:00~20:30)으로 유니버스에 새로 진입한 종목은 라벨이
    없다(KRX 마감 후라 순위 변동이 거의 없어 실질 영향 미미).
  - 리스크 지표는 dt < 오늘 조건으로 T-1 행을 고른다 — 당일 행은 집계 전(0/빈값)이거나
    저녁에 확정 공표되어 선정 시점(15시)에 알 수 없던 값이므로 쓰지 않는다(누수 방지).

[cron] 두 회차로 돈다(scheduler.JOBS).
  · 14:30 `--risk-only` — **T-1 확정 리스크 3종만**. KRX 매수(15:20)·NXT 매수(19:50) 선정
    회차가 이 값을 보게 하는 것이 목적이다. 17:50 회차와 **같은 값**이 나온다(`dt < 오늘`
    행만 고르므로 시각 무관) → 채점 표본과 집행 값이 같은 변수로 유지된다.
  · 17:50 전체 — 시간외(ah_*)·체결강도·breadth 까지. ka10087 이 16~18시에만 살아있어 이 시각.
단발 실행: uv run workers/after_hours_labels.py [--risk-only]
"""
import logging
import time
from datetime import datetime

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
from core.repository.stock_report import get_report_codes, save_after_hours_labels
from core.repository.market_snapshot import save_after_hours_breadth

setup_logging()
logger = logging.getLogger("AfterHoursLabels")

_SLEEP = 0.25          # 키움 레이트리밋 여유 (서버측 429 재시도와 별개의 예방 간격)
_BREADTH_PCT = 3.0     # 시간외 급등/급락 판정 임계(%)


def _f(v) -> float | None:
    """키움 부호 포함 문자열('+9.98', '-0', '') → float. 빈값/무효는 None."""
    try:
        s = str(v).replace("+", "").replace(",", "").strip()
        if s in ("", "-"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


def _prev_rows(items: list[dict], today_dt: str, limit: int = 5) -> list[dict]:
    """일별 시계열에서 dt < 오늘인 최근 행 limit 개(최신순 응답 가정)."""
    return [it for it in items if (it.get("dt") or "") < today_dt][:limit]


def _risk_labels(api: KiwoomRestClient, code: str, today_dt: str, row: dict) -> dict:
    """T-1 확정 리스크 라벨 3종을 row 에 채운다(제자리 수정 + 반환).

    전부 `dt < 오늘` 행만 고르므로 **하루 중 언제 수집해도 같은 값**이다 — 14:30 회차와
    17:50 회차가 같은 값을 쓰는 근거이자, 이 컬럼들이 선정 시점에 실행 가능한 이유다
    (core/edge_policy.SELECTION_TIME_COLS 주석 참고).
    """
    # 신용융자 잔고율 (ka10013) — T-1 확정행
    try:
        d = api.get_credit_trade_trend(code)
        prev = [
            it for it in _prev_rows(d.get("crd_trde_trend", []), today_dt)
            if _f(it.get("remn_rt")) is not None
        ]
        if prev:
            row["credit_remn_rt"] = _f(prev[0].get("remn_rt"))
    except Exception as e:
        logger.warning(f"신용매매동향 조회 실패 [{code}]: {e}")
    time.sleep(_SLEEP)

    # 공매도 비중 (ka10014) — T-1 + 직전 5일 평균
    try:
        d = api.get_short_sale_trend(code)
        prev = _prev_rows(d.get("shrts_trnsn", []), today_dt)
        wghts = [w for w in (_f(it.get("trde_wght")) for it in prev) if w is not None]
        if wghts:
            row["short_wght"] = wghts[0]
            row["short_wght_5d"] = round(sum(wghts) / len(wghts), 2)
    except Exception as e:
        logger.warning(f"공매도추이 조회 실패 [{code}]: {e}")
    time.sleep(_SLEEP)

    # 대차 잔고 (ka20068) — T-1 잔고주수 + 직전 5일 증감 합
    try:
        d = api.get_stock_lending_trend(code)
        prev = _prev_rows(d.get("dbrt_trde_trnsn", []), today_dt)
        if prev:
            row["lend_remn"] = _i(prev[0].get("rmnd"))
            irds = [v for v in (_i(it.get("dbrt_trde_irds")) for it in prev) if v is not None]
            if irds:
                row["lend_irds_5d"] = sum(irds)
    except Exception as e:
        logger.warning(f"대차거래추이 조회 실패 [{code}]: {e}")
    time.sleep(_SLEEP)

    return row


def _stock_labels(api: KiwoomRestClient, code: str, today_dt: str,
                  risk_only: bool = False) -> dict:
    """종목 하나의 라벨 dict 구성. 개별 TR 실패는 해당 라벨만 NULL(수집은 계속).

    risk_only=True 면 **T-1 확정 리스크 3종만** 수집한다(매수 직전 14:30 회차용).
    시간외(ah_*)·체결강도는 당일 세션 값이라 그 시각엔 아직 존재하지 않으므로 건너뛴다 —
    저장은 COALESCE 라 건너뛴 컬럼은 17:50 회차가 채울 때까지 기존 값이 보존된다.
    """
    row: dict = {"stock_code": code}
    if risk_only:
        return _risk_labels(api, code, today_dt, row)

    # 시간외단일가 (ka10087) — 세션 중(16~18시)에만 유효. 체결 0주면 NULL 유지
    # (세션 종료 후 이 TR 은 등락률·거래량을 0으로 리셋하므로 0 을 저장하면 오염된다)
    try:
        d = api.get_after_hours_single_price(code)
        px = _i(d.get("ovt_sigpric_cur_prc"))
        vol = _i(d.get("ovt_sigpric_acc_trde_qty"))
        if px and vol:
            row["ah_price"] = abs(px)
            row["ah_flu_rt"] = _f(d.get("ovt_sigpric_flu_rt"))
            row["ah_volume"] = vol
    except Exception as e:
        logger.warning(f"시간외단일가 조회 실패 [{code}]: {e}")
    time.sleep(_SLEEP)

    # 시간외 초과반응 ah_react = 시간외단일가 ÷ 당일 KRX 종가 − 1 (%).
    # 앵커는 수정주가 일봉의 당일 캔들 종가 — 리포트 행의 change_pct 는 저녁 재실행에서
    # NXT 가격에 오염될 수 있어 쓰지 않는다. rule predicate 는 컬럼 간 비교가 안 되므로
    # 여기서 파생값으로 구워야 실험실 rule 이 쓸 수 있다.
    if row.get("ah_price"):
        try:
            d = api.get_daily_chart(code)
            candles = d.get("stk_dt_pole_chart_qry", [])
            if candles and candles[0].get("dt") == today_dt:
                close = abs(_i(candles[0].get("cur_prc")) or 0)
                if close > 0:
                    row["ah_react"] = round((row["ah_price"] / close - 1) * 100, 2)
        except Exception as e:
            logger.warning(f"KRX 종가(ah_react 앵커) 조회 실패 [{code}]: {e}")
        time.sleep(_SLEEP)

    _risk_labels(api, code, today_dt, row)

    # 체결강도 (ka10047) — 첫 행이 당일(마감 확정치)
    try:
        d = api.get_execution_strength_daily(code)
        items = d.get("cntr_str_daly", [])
        if items and (items[0].get("dt") or "") == today_dt:
            row["exec_str"] = _f(items[0].get("cntr_str"))
            row["exec_str_5d"] = _f(items[0].get("cntr_str_5min"))  # 필드명은 min, 실제 5일 평균
    except Exception as e:
        logger.warning(f"체결강도 조회 실패 [{code}]: {e}")
    time.sleep(_SLEEP)

    return row


def _market_breadth(api: KiwoomRestClient) -> tuple[int | None, int | None]:
    """ka10098 상승률/하락률 순위에서 ±3% 이상 종목 수. 페이지 끝까지 임계 초과면
    하한값(로그로 표시). 실패 시 None."""
    up3 = dn3 = None
    for sort_base, sign in (("1", 1), ("3", -1)):
        try:
            d = api.get_after_hours_flu_rank(sort_base=sort_base)
            items = d.get("ovt_sigpric_flu_rt_rank", [])
            cnt = 0
            for it in items:
                flu = _f(it.get("flu_rt"))
                if flu is None or sign * flu < _BREADTH_PCT:
                    break
                cnt += 1
            if items and cnt == len(items):
                logger.info(f"시간외 breadth(sort={sort_base}) 페이지 전체 임계 초과 — 하한값 {cnt}")
            if sign > 0:
                up3 = cnt
            else:
                dn3 = cnt
        except Exception as e:
            logger.warning(f"시간외 등락률 순위 조회 실패 (sort={sort_base}): {e}")
        time.sleep(_SLEEP)
    return up3, dn3


def run(risk_only: bool = False):
    today = datetime.now()
    today_iso = today.strftime("%Y-%m-%d")
    today_dt = today.strftime("%Y%m%d")

    codes = get_report_codes(today_iso)
    if not codes:
        logger.info(f"{today_iso} 유니버스 없음 — 종료")
        return

    api = KiwoomRestClient()
    api.ensure_token()

    what = "리스크 라벨(T-1 확정)" if risk_only else "시간외·리스크 라벨"
    logger.info(f"{what} 수집 시작 — 유니버스 {len(codes)}종목")
    rows = []
    for code in codes:
        base = code.split("_")[0]
        rows.append(_stock_labels(api, base, today_dt, risk_only=risk_only))
    n = save_after_hours_labels(today_iso, rows)
    if risk_only:
        filled = sum(1 for r in rows if r.get("short_wght") is not None)
        logger.info(f"리스크 라벨 저장 {n}행 (공매도 비중 {filled}/{len(rows)}종목)")
        return   # breadth 는 시간외 세션 지표라 이 회차에선 수집하지 않는다

    filled_ah = sum(1 for r in rows if r.get("ah_price") is not None)
    logger.info(f"종목 라벨 저장 {n}행 (시간외 체결 {filled_ah}/{len(rows)}종목)")

    up3, dn3 = _market_breadth(api)
    save_after_hours_breadth(today_iso, up3, dn3)
    logger.info(f"시장 breadth 저장 — 시간외 +3%↑ {up3}종목 / -3%↓ {dn3}종목")


if __name__ == "__main__":
    import argparse

    from core.market_calendar import exit_if_not_trading_day

    parser = argparse.ArgumentParser(description="시간외·리스크 라벨 수집")
    parser.add_argument(
        "--risk-only", action="store_true",
        help="T-1 확정 리스크 라벨만 수집(매수 직전 14:30 회차 — 시간외·체결강도는 스킵)",
    )
    args = parser.parse_args()
    exit_if_not_trading_day()
    run(risk_only=args.risk_only)
