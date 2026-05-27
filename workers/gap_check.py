"""갭상승 체크 워커
전날 daily_stock_report Top 10의 '리포트 시각 → 현재가' 등락률을 ADMIN 유저에게 전송

- 평일 08:10: 기본 실행. NXT 가격 조회. 미지원 등으로 대기 중인 종목은
  state 파일에 저장하고 '⏳ 장 시작 대기' 섹션에 표시.
- 평일 09:10: --retry 실행. 전체 종목을 KRX로 재조회.
  8:10 NXT 결과가 있는 종목은 [NXT]/[KRX] 두 줄로 표시하고,
  갭 상승/하락 분류는 리포트 → 9:10 KRX 최종 등락률 기준.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from core.logging_setup import setup_logging
from core.kiwoom_api import KiwoomConfig, KiwoomRestAPI
from core.trading_engine import AnalysisEngine
from core.repository.stock_report import (
    get_stock_report_dates,
    get_stock_reports_by_date,
    save_gap_check_results,
)
from core.notifications import send_gap_check_alert

setup_logging()
logger = logging.getLogger("GapCheck")

STATE_FILE = Path(__file__).resolve().parent.parent / ".gap_check_pending.json"


def _most_recent_prior_date() -> str | None:
    dates = get_stock_report_dates(limit=5)
    today = datetime.now().date().isoformat()
    return next((d for d in dates if d < today), None)


def _query_stocks(
    reports: list[dict],
    detect_pending: bool,
    stk_postfix: str = "",
) -> list[dict]:
    """
    stk_postfix: ka10001 stk_cd 접미사 — ""=KRX, "_NX"=NXT, "_AL"=SOR
    detect_pending=True면 조회 실패/빈값을 pending으로 분류 (09:10 재조회 대상)
    """
    api = KiwoomRestAPI(KiwoomConfig())
    api.ensure_token()
    rows = []
    for r in reports:
        rank = r["rank_no"]
        name = r["stock_name"]
        code = r["stock_code"]
        stk_cd = code.split(".")[0] + stk_postfix
        report_price = abs(int(r.get("current_price") or 0))
        score = int(r.get("score") or 0)
        base = {"rank": rank, "name": name, "score": score}
        try:
            info = api.get_stock_basic_info(stk_cd)
            now_price = abs(AnalysisEngine.parse_price(info.get("cur_prc", "0")))
            if report_price <= 0:
                rows.append({**base, "error": True})
                continue
            if now_price <= 0:
                if detect_pending:
                    rows.append({**base, "code": code, "report_price": report_price, "pending": True})
                else:
                    rows.append({**base, "error": True})
                continue
            pct = (now_price - report_price) / report_price * 100
            rows.append({
                **base,
                "code": code,
                "report_price": report_price, "now_price": now_price,
                "pct": pct,
            })
        except Exception as e:
            logger.warning(f"{name}({stk_cd}) 조회 실패: {e}")
            if detect_pending:
                rows.append({**base, "code": code, "report_price": report_price, "pending": True})
            else:
                rows.append({**base, "error": True})
    return rows


def _save_state(report_date: str, rows: list[dict]):
    """retry에서 전체 종목을 KRX로 재조회하기 위해 항상 저장"""
    if not rows:
        STATE_FILE.unlink(missing_ok=True)
        return
    pending_count = sum(1 for r in rows if r.get("pending"))
    STATE_FILE.write_text(
        json.dumps({"report_date": report_date, "rows": rows}, ensure_ascii=False)
    )
    logger.info(f"state 저장 → 총 {len(rows)}건 (대기 {pending_count}건)")


def _load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception as e:
        logger.warning(f"state 파일 로드 실패: {e}")
        return None


def run_initial():
    logger.info("=" * 60)
    logger.info("갭상승 체크 시작")
    logger.info("=" * 60)

    STATE_FILE.unlink(missing_ok=True)

    report_date = _most_recent_prior_date()
    if not report_date:
        logger.info("전날 리포트 없음 — 종료")
        return

    reports = get_stock_reports_by_date(report_date)[:10]
    if not reports:
        logger.info(f"{report_date} 리포트 데이터 없음 — 종료")
        return

    logger.info(f"{report_date} Top {len(reports)} 종목의 NXT 현재가 조회 중...")

    rows = _query_stocks(reports, detect_pending=True, stk_postfix="_NX")
    _save_state(report_date, rows)

    try:
        save_gap_check_results(report_date, rows)
    except Exception as e:
        logger.warning(f"갭 체크 결과 DB 저장 실패: {e}")

    check_time = datetime.now().strftime("%m-%d %H:%M")
    send_gap_check_alert(report_date, check_time, rows)
    logger.info("갭상승 체크 완료")


def run_retry():
    logger.info("=" * 60)
    logger.info("갭상승 체크 재조회 시작")
    logger.info("=" * 60)

    state = _load_state()
    if not state or not state.get("rows"):
        logger.info("state 없음 — 종료")
        return

    report_date = state["report_date"]
    all_rows = state["rows"]
    candidates = [r for r in all_rows if not r.get("error")]
    if not candidates:
        logger.info("재조회 대상 없음 — 종료")
        return

    logger.info(f"{report_date} 종목 {len(candidates)}개 KRX 재조회 중...")

    code_by_rank = {
        r["rank_no"]: r["stock_code"]
        for r in get_stock_reports_by_date(report_date)[:10]
    }

    krx_inputs = [{
        "rank_no": r["rank"],
        "stock_name": r["name"],
        "stock_code": r.get("code") or code_by_rank.get(r["rank"]),
        "current_price": r["report_price"],
        "score": r["score"],
    } for r in candidates]

    krx_rows = _query_stocks(krx_inputs, detect_pending=False, stk_postfix="")
    krx_by_rank = {k["rank"]: k for k in krx_rows}

    merged = []
    for r in all_rows:
        if r.get("error"):
            merged.append(r)
            continue

        krx = krx_by_rank.get(r["rank"], {})
        krx_ok = "now_price" in krx and not krx.get("error")
        nxt_ok = not r.get("pending") and "now_price" in r

        if not krx_ok and not nxt_ok:
            merged.append({
                "rank": r["rank"], "name": r["name"], "score": r["score"],
                "error": True,
            })
            continue

        out = {
            "rank": r["rank"], "name": r["name"], "score": r["score"],
            "report_price": r["report_price"],
        }
        if nxt_ok:
            out["nxt_price"] = r["now_price"]
            out["nxt_pct"] = r["pct"]
        if krx_ok:
            out["krx_price"] = krx["now_price"]
            out["krx_pct"] = krx["pct"]
            if nxt_ok and r["now_price"] > 0:
                out["krx_from_nxt_pct"] = (
                    (krx["now_price"] - r["now_price"]) / r["now_price"] * 100
                )
        merged.append(out)

    try:
        save_gap_check_results(report_date, merged)
    except Exception as e:
        logger.warning(f"갭 체크 결과 DB 저장 실패: {e}")

    check_time = datetime.now().strftime("%m-%d %H:%M")
    send_gap_check_alert(report_date, check_time, merged, is_retry=True)
    STATE_FILE.unlink(missing_ok=True)
    logger.info("갭상승 체크 재조회 완료")


if __name__ == "__main__":
    if "--retry" in sys.argv:
        run_retry()
    else:
        run_initial()
