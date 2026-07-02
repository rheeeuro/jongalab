"""익일 시가 결과 백필 워커 — daily_stock_report.next_open_ret 채우기.

엣지 연구용: 선정(selected=1)/비선정(0) 유니버스 전 종목에 '리포트일 종가 → 다음 거래일 시가'
등락률(%)을 **균일 기준**으로 부여한다(종가베팅은 종가 매수라 종가 앵커가 실제 진입에 가깝다).
어떤 요인이 승자/패자를 가르는지 사후 측정하려면 선정 종목만이 아니라 유니버스 전체의 결과
라벨이 필요하다(gap_check 는 top-10 만 채움).

[동작]
  - 오늘 이전(report_date < CURDATE) 이면서 next_open_ret 이 비어있는 행을 대상으로,
    키움 수정주가 일봉(ka10081)에서 리포트일 종가 → 다음 첫 거래일 시가 등락률을 계산.
  - **분할 정합성**: 원주가(저장된 current_price) 대신 수정주가 차트 내부의 종가·시가만 써서
    분할을 상쇄한다. 넘는 ±35%(일일 등락제한 여유)는 분할/데이터 아티팩트로 보고 스킵.
  - 종목 일봉은 1회 조회분(약 600거래일)에 필요한 날짜가 모두 들어있으므로 종목당 1회만 조회(캐시).
  - '다음 거래일 시가'가 아직 없는 최근 날짜는 다음 실행에서 자동 재시도(NULL 유지).

[cron] 매 거래일 09:30 (전 거래일 리포트에 당일 시가가 반영된 뒤). 단발 실행: python workers/outcome_backfill.py [YYYY-MM-DD]
"""
import logging
import sys
from datetime import datetime

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
from core.trading_engine import AnalysisEngine
from core.repository.stock_report import (
    get_dates_missing_outcome,
    get_rows_missing_outcome,
    save_next_open_ret,
)

setup_logging()
logger = logging.getLogger("OutcomeBackfill")


# 한 세션 오버나이트 등락 상한(%) — KR 일일 등락제한 ±30% 여유. 넘으면 분할·데이터 아티팩트로 보고 스킵.
_SANE_RET_PCT = 35.0


def _build_ohlc_by_date(api: KiwoomRestClient, code: str) -> dict[str, tuple[int, int]]:
    """{YYYYMMDD: (시가, 종가)} 맵 (수정주가 일봉 1회 조회)."""
    try:
        data = api.get_daily_chart(code)
    except Exception as e:
        logger.warning(f"[{code}] 일봉 조회 실패: {e}")
        return {}
    m: dict[str, tuple[int, int]] = {}
    for c in data.get("stk_dt_pole_chart_qry", []):
        dt = c.get("dt", "")
        op = abs(AnalysisEngine.parse_price(c.get("open_pric", "0")))
        cl = abs(AnalysisEngine.parse_price(c.get("cur_prc", "0")))
        if len(dt) == 8 and op > 0 and cl > 0:
            m[dt] = (op, cl)
    return m


def _overnight_ret(ohlc: dict[str, tuple[int, int]], report_dt: str, today_dt: str) -> float | None:
    """리포트일 종가 → 다음 '완결된' 거래일 시가 등락률(%). 없거나 비정상이면 None.

    수정주가 차트 내부의 종가·시가만 쓰므로 분할이 상쇄된다(원주가 참조 금지 → 분할 아티팩트 제거).
    오늘 캔들은 장중이라 시가가 placeholder(전일 종가)이므로 today_dt 이상은 제외.
    """
    if report_dt not in ohlc:
        return None  # 리포트일이 차트 범위 밖(오래됨) 또는 미거래 → 앵커 불가
    report_close = ohlc[report_dt][1]
    if report_close <= 0:
        return None
    later = sorted(d for d in ohlc if report_dt < d < today_dt)
    if not later:
        return None
    next_open = ohlc[later[0]][0]
    ret = (next_open - report_close) / report_close * 100
    if abs(ret) > _SANE_RET_PCT:
        logger.warning(f"비정상 등락 스킵: {report_dt}→{later[0]} {ret:+.1f}% (분할/데이터 아티팩트 의심)")
        return None
    return round(ret, 3)


def run(min_date: str | None = None):
    dates = get_dates_missing_outcome(min_date)
    if not dates:
        logger.info("백필 대상 없음 — 종료")
        return

    api = KiwoomRestClient()
    api.ensure_token()
    today_dt = datetime.now().strftime("%Y%m%d")
    logger.info(f"결과 백필 대상 {len(dates)}일: {dates[0]} ~ {dates[-1]}")

    cache: dict[str, dict[str, tuple[int, int]]] = {}
    total = 0
    for d in dates:
        rows = get_rows_missing_outcome(d)
        report_dt = d.replace("-", "")
        results = []
        for r in rows:
            stored_code = r["stock_code"]
            code = stored_code.split("_")[0].split(".")[0]
            if code not in cache:
                cache[code] = _build_ohlc_by_date(api, code)
            ret = _overnight_ret(cache[code], report_dt, today_dt)
            if ret is None:
                continue
            results.append({"stock_code": stored_code, "next_open_ret": ret})
        n = save_next_open_ret(d, results)
        total += n
        logger.info(f"{d}: {n}/{len(rows)}행 백필")
    logger.info(f"결과 백필 완료 — 총 {total}행")


if __name__ == "__main__":
    min_date = sys.argv[1] if len(sys.argv) > 1 else None
    run(min_date)
