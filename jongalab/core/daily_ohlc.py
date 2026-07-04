"""수정주가 일봉(ka10081) 파싱 + 결과 라벨 아티팩트 가드 — **라벨 경로 공유 모듈**.

outcome_backfill(일봉 라벨 4종)과 gap_check --label-nxt(08:06 프리마켓 라벨)가 함께 쓴다.
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
