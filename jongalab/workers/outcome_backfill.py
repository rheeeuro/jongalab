"""익일 결과 라벨 백필 워커 — 일봉 결과 라벨 4종 + 실집행 레그 라벨 + 후속 재료 실현 일수.

엣지 연구용: 선정(selected=1)/비선정(0) 유니버스 전 종목에 '리포트일 종가 → 다음 거래일
(시가·고가·저가·종가)' 등락률(%)을 **균일 기준**으로 부여한다(종가베팅은 종가 매수라 종가
앵커가 실제 진입에 가깝다). 4종은 같은 일봉 1회 조회에서 파생 — 추가 API 콜 0.
  next_open_ret  — 익일 시가(진입 다음 첫 체결점)
  next_high_ret  — 익일 고가(이론상 최대 실현 가능치)
  next_low_ret   — 익일 저가(꼬리 리스크·하드 손절 관통)
  next_close_ret — 익일 종가(홀드 시나리오)
  exec_leg_ret   — 실제 청산 venue 창(NXT 19:50→08:03 / KRX 15:20→09:03)
어떤 요인이 승자/패자를 가르는지, 어떤 청산창이 유리한지 사후 측정하려면 선정 종목만이
아니라 유니버스 전체의 결과 라벨이 필요하다(gap_check 는 top-10 만 채움).

[동작]
  - 오늘 이전(report_date < CURDATE) 이면서 라벨 4종 중 하나라도 비어있는 행을 대상으로,
    키움 수정주가 일봉(ka10081)에서 리포트일 종가 → 다음 첫 거래일 OHLC 등락률을 계산.
  - **분할 정합성**: 원주가(저장된 current_price) 대신 수정주가 차트 내부의 종가·시가만 써서
    분할을 상쇄한다. 넘는 ±35%(일일 등락제한 여유)는 분할/데이터 아티팩트로 보고 스킵.
  - 종목 일봉은 1회 조회분(약 600거래일)에 필요한 날짜가 모두 들어있으므로 종목당 1회만 조회(캐시).
  - '다음 거래일 시가'나 09:03 실집행 레그가 아직 없는 최근 날짜는 다음 실행에서 자동 재시도(NULL 유지).
  - exec_leg_ret 은 NXT 양 끝(19:50·08:03) 가격이 모두 있으면 NXT, 아니면 KRX(15:20·09:03)로 계산한다.
  - exec_leg_ret 은 활성 rule 의 registered_at 이후만 백필한다(평가에 안 쓰는 과거 분봉 조회 방지).
  - **권리락 가드**: 다음 거래일이 권리락일(무상증자·분할)이면 일봉만 소급 조정되고 분봉·NXT
    시세는 실거래가라, 미조정 가격으로 만드는 라벨(exec_leg_ret·nxt_open_ret)에 배정비율이
    그대로 손실로 찍힌다. 수정 일봉 종가 ↔ 저장된 krx_close_price 의 스케일 불일치로 감지해
    exec_leg_ret 은 비우고 nxt_open_ret 은 되돌린다(daily_ohlc.is_price_scale_shifted).
    일봉 라벨 4종은 양 끝이 모두 조정 스케일이라 정상이므로 손대지 않는다.

[후속 재료 실현 채점 — news_followup_days]
  뉴스 재료 지속성 라벨(news_durability, sql/40)이 **맞았는지** 채점하는 유일한 사후 값이다.
  리포트일 +1 ~ +NEWS_FOLLOWUP_WINDOW_DAYS 일 사이에 그 종목의 **시세보도가 아닌** 언급이 있던
  날짜 수를 센다(DB·순수 로직만, API 콜 0). 창이 열려 있는 동안 매 실행 재계산(멱등)하고
  창이 닫히면 값이 확정된다. 시세보도 제외와 '일수' 채점의 이유는 sql/40 주석 참조.

[cron] 매 거래일 09:30 (전 거래일 리포트에 당일 시가가 반영된 뒤). 단발 실행: python workers/outcome_backfill.py [YYYY-MM-DD]
"""
import logging
import sys
from datetime import datetime, timedelta

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
from core.daily_ohlc import (
    SANE_RET_PCT,
    build_ohlc_by_date,
    build_minute_price_by_time,
    first_later_chart_date,
    first_price_at_or_after,
    is_price_scale_shifted,
    ret_pct,
)
from core.config import NEWS_FOLLOWUP_WINDOW_DAYS
from core.news_material_judge import count_followup_days
from core.repository.news import get_news_days_by_stocks
from core.repository.stock_report import (
    get_dates_missing_outcome,
    get_rows_missing_outcome,
    save_outcome_labels,
    get_dates_missing_exec_leg,
    get_rows_missing_exec_leg,
    save_exec_leg_labels,
    clear_nxt_open_labels,
    get_rows_for_news_followup,
    save_news_followup,
)
from core.repository.edge_rule import list_rules

setup_logging()
logger = logging.getLogger("OutcomeBackfill")


def _earliest_exec_label_registered_at() -> str | None:
    """exec_leg_ret 를 실제로 쓰는 rule 의 가장 이른 registered_at.

    exec_leg_ret 은 분봉 조회 비용이 커서, evaluator 가 채점하지 않을 과거 날짜는 백필하지 않는다.
    retired 도 evaluator 가 계속 채점하므로(2026-07-31) 여기서도 포함한다.
    """
    dates = [
        str(r["registered_at"])
        for r in list_rules()
        if r.get("exit_label") == "exec_leg_ret" and r.get("registered_at")
    ]
    return min(dates) if dates else None


def _overnight_rets(
    ohlc: dict[str, tuple[int, int, int, int]], report_dt: str, today_dt: str
) -> dict | None:
    """리포트일 종가 → 다음 '완결된' 거래일 (시가·고가·저가·종가) 등락률(%) 4종.

    앵커는 리포트일 종가. 없거나 시가가 비정상(±35% 초과 아티팩트)이면 행 전체 스킵(None).
    수정주가 차트 내부 값만 쓰므로 분할이 상쇄된다(원주가 참조 금지). 오늘 캔들은 장중이라
    시가가 placeholder 이므로 today_dt 이상은 제외. ±35% 가드는 4개 라벨에 동일 적용.
    """
    if report_dt not in ohlc:
        return None  # 리포트일이 차트 범위 밖(오래됨) 또는 미거래 → 앵커 불가
    report_close = ohlc[report_dt][3]
    if report_close <= 0:
        return None
    later = sorted(d for d in ohlc if report_dt < d < today_dt)
    if not later:
        return None
    op, hi, lo, cl = ohlc[later[0]]

    def _ret(px: int) -> float | None:
        if px <= 0:
            return None
        r = (px - report_close) / report_close * 100
        if abs(r) > SANE_RET_PCT:
            return None  # 분할/데이터 아티팩트
        return round(r, 3)

    open_ret = _ret(op)
    if open_ret is None:
        logger.warning(f"비정상/무효 시가 스킵: {report_dt}→{later[0]} (분할/데이터 아티팩트 의심)")
        return None
    return {
        "next_open_ret": open_ret,
        "next_high_ret": _ret(hi),
        "next_low_ret": _ret(lo),
        "next_close_ret": _ret(cl),
    }


def _exec_leg_label(
    api: KiwoomRestClient,
    code: str,
    report_dt: str,
    next_dt: str,
    nxt_allowed: bool,
    minute_cache: dict[tuple[str, bool, str], dict[str, int]],
) -> dict | None:
    """실집행 venue 창 하나를 선택해 {exec_leg_ret, exec_leg_venue} 반환.

    NXT 기준가·청산가가 모두 있으면 NXT(19:50→08:03)를 우선한다. 둘 중 하나라도 없으면
    KRX(15:20→09:03)로 폴백한다. 같은 venue 양 끝 가격이 모두 있어야 라벨을 채운다.
    """

    def _prices(nxt: bool, base_dt: str) -> dict[str, int]:
        key = (code, nxt, base_dt)
        if key not in minute_cache:
            minute_cache[key] = build_minute_price_by_time(
                api, code, nxt=nxt, base_dt=base_dt, max_pages=2
            )
        return minute_cache[key]

    # 창 시각(19:50/08:03/15:20/09:03)은 trading 의 실집행 스케줄 미러다
    # (signal_executor 매수 데드라인 15:20/19:50, settle 청산 08:03/09:03).
    # trading 쪽 시각을 바꾸면 이 라벨도 함께 바꿔야 비교가 유효하다.
    def _leg(venue: str, nxt: bool, base_hm: str, exit_hm: str) -> dict | None:
        base = first_price_at_or_after(_prices(nxt, report_dt), report_dt + base_hm)
        exit_ = first_price_at_or_after(_prices(nxt, next_dt), next_dt + exit_hm)
        if not base or not exit_:
            return None
        r = ret_pct(base[1], exit_[1])
        if r is None:
            logger.warning(
                f"비정상 실집행 레그 스킵 [{code}/{venue}]: "
                f"{base[0]} {base[1]} → {exit_[0]} {exit_[1]}"
            )
            return None
        return {"exec_leg_ret": r, "exec_leg_venue": venue}

    if nxt_allowed:
        nxt = _leg("NXT", True, "1950", "0803")
        if nxt is not None:
            return nxt
        # NXT 미상장일 수도, 일시적 분봉 결측일 수도 있다 — 폴백이 라벨에 고착되므로 흔적을 남긴다.
        logger.info(f"[{code}] NXT 레그 결측 → KRX 폴백 ({report_dt}→{next_dt})")
    return _leg("KRX", False, "1520", "0903")


def _run_daily_outcome(
    api: KiwoomRestClient,
    dates: list[str],
    cache: dict[str, dict[str, tuple[int, int, int, int]]],
) -> int:
    if not dates:
        return 0
    today_dt = datetime.now().strftime("%Y%m%d")
    logger.info(f"일봉 결과 백필 대상 {len(dates)}일: {dates[0]} ~ {dates[-1]}")

    total = 0
    for d in dates:
        rows = get_rows_missing_outcome(d)
        report_dt = d.replace("-", "")
        results = []
        for r in rows:
            stored_code = r["stock_code"]
            code = stored_code.split("_")[0].split(".")[0]
            if code not in cache:
                cache[code] = build_ohlc_by_date(api, code)
            rets = _overnight_rets(cache[code], report_dt, today_dt)
            if rets is None:
                continue
            results.append({"stock_code": stored_code, **rets})
        n = save_outcome_labels(d, results)
        total += n
        logger.info(f"{d}: 일봉 {n}/{len(rows)}행 백필")
    return total


def _run_exec_leg(
    api: KiwoomRestClient,
    dates: list[str],
    cache: dict[str, dict[str, tuple[int, int, int, int]]],
) -> int:
    if not dates:
        return 0
    logger.info(f"실집행 레그 백필 대상 {len(dates)}일: {dates[0]} ~ {dates[-1]}")

    minute_cache: dict[tuple[str, bool, str], dict[str, int]] = {}
    total = 0
    for d in dates:
        rows = get_rows_missing_exec_leg(d)
        report_dt = d.replace("-", "")
        results = []
        ex_rights: list[str] = []
        for r in rows:
            stored_code = r["stock_code"]
            code = stored_code.split("_")[0].split(".")[0]
            if code not in cache:
                cache[code] = build_ohlc_by_date(api, code)
            next_dt = first_later_chart_date(cache[code], report_dt)
            if not next_dt:
                continue
            # 권리락 가드 — 다음 거래일이 권리락일이면 수정주가 일봉만 소급 조정되고 분봉·NXT
            # 시세는 실거래가를 그대로 준다. 그 상태로 계산하면 배정비율이 그대로 손실로 찍히고
            # ±SANE_RET_PCT 도 통과한다(daily_ohlc.is_price_scale_shifted 주석의 대동기어 실측).
            # 갭·수급이 아닌 기계적 조정이므로 채점 표본에서 빼는 게 맞다 — 일봉 라벨 4종은
            # 양 끝이 모두 조정 스케일이라 정상이고, 여기서 손대지 않는다.
            adj_close = (cache[code].get(report_dt) or (0, 0, 0, 0))[3]
            if is_price_scale_shifted(adj_close, r.get("krx_close_price")):
                logger.info(
                    f"[{code}] 권리락 감지 → 미조정 라벨 제외 "
                    f"(수정 일봉 종가 {adj_close} vs 실거래 종가 {r.get('krx_close_price')})"
                )
                ex_rights.append(stored_code)
                continue
            label = _exec_leg_label(
                api, code, report_dt, next_dt, r.get("nxt_listed") != 0, minute_cache
            )
            if label is None:
                continue
            results.append({"stock_code": stored_code, **label})
        n = save_exec_leg_labels(d, results)
        total += n
        logger.info(f"{d}: 실집행 레그 {n}/{len(rows)}행 백필")
        # 같은 원인(권리락)으로 오염되는 08:06 NXT 프리마켓 라벨도 함께 되돌린다.
        # gap_check 는 그 시점에 권리락을 구분할 수 없어 저장했고, 정리는 여기 한 곳에서 한다.
        if ex_rights:
            cleared = clear_nxt_open_labels(d, ex_rights)
            logger.info(f"{d}: 권리락 {len(ex_rights)}종목 — NXT 프리마켓 라벨 {cleared}행 무효화")
    return total


def _run_news_followup(window_days: int = NEWS_FOLLOWUP_WINDOW_DAYS) -> int:
    """news_followup_days 채점 — DB·순수 로직만(키움 API 콜 0).

    창이 열려 있는 행은 매 실행 재계산한다(창이 자라며 값이 단조 증가). 종목별 언급은 필요한
    전 구간을 **한 번에** 받아 행마다 Python 에서 창을 자른다 — 행마다 쿼리하면 하루 16종목 ×
    창 일수만큼 쿼리가 늘어난다.
    """
    rows = get_rows_for_news_followup(window_days)
    if not rows:
        logger.info("후속 재료 채점 대상 없음 — 건너뜀")
        return 0

    codes = sorted({r["stock_code"].split("_")[0].split(".")[0] for r in rows})
    start = min(r["report_date"] for r in rows) + timedelta(days=1)
    end = max(r["report_date"] for r in rows) + timedelta(days=window_days)
    mentions = get_news_days_by_stocks(codes, start, end)

    results = []
    for r in rows:
        code = r["stock_code"].split("_")[0].split(".")[0]
        lo = r["report_date"] + timedelta(days=1)
        hi = r["report_date"] + timedelta(days=window_days)
        window = [m for m in mentions.get(code, []) if lo <= m["d"] <= hi]
        results.append({
            "report_date": r["report_date"],
            "stock_code": r["stock_code"],
            "news_followup_days": count_followup_days(window),
        })
    n = save_news_followup(results)
    logger.info(f"후속 재료 채점 {n}행 (창 {window_days}일, 대상 {len(rows)}행)")
    return n


def run(min_date: str | None = None):
    # 후속 재료 채점은 키움 API 를 안 쓰므로 일봉 백필 대상이 없어도(또는 토큰이 없어도) 돈다.
    # 실패해도 가격 라벨 백필을 막지 않는다(연구 라벨 vs 결과 라벨 분리).
    try:
        _run_news_followup()
    except Exception as e:
        logger.warning(f"후속 재료 채점 실패(가격 라벨 백필은 계속): {e}")

    outcome_dates = get_dates_missing_outcome(min_date)
    exec_min_date = min_date or _earliest_exec_label_registered_at()
    if exec_min_date:
        exec_dates = get_dates_missing_exec_leg(exec_min_date)
    else:
        # exec_leg_ret 를 쓰는 활성 rule 이 없으면 스킵 — min_date 게이트 없이 진행하면
        # 라벨이 빈 과거 전체가 분봉 백필 대상이 되는 폭주로 이어진다.
        exec_dates = []
        logger.info("exec_leg_ret 활성 rule 없음 — 실집행 레그 백필 건너뜀")
    if not outcome_dates and not exec_dates:
        logger.info("일봉·실집행 백필 대상 없음 — 종료")
        return

    api = KiwoomRestClient()
    api.ensure_token()
    cache: dict[str, dict[str, tuple[int, int, int, int]]] = {}

    outcome_total = _run_daily_outcome(api, outcome_dates, cache)
    exec_total = _run_exec_leg(api, exec_dates, cache)
    logger.info(f"결과 백필 완료 — 일봉 {outcome_total}행 / 실집행 레그 {exec_total}행")


if __name__ == "__main__":
    min_date = sys.argv[1] if len(sys.argv) > 1 else None
    run(min_date)
