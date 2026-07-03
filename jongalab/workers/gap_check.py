"""갭상승 체크 워커 — 실매매 청산 창(venue별)에 맞춘 갭 측정

측정 창 (실제 종가베팅 매수→청산 시각과 일치):
  NXT 상장 종목: 전일 19:50 NXT 가격 → 당일 08:03 NXT 가격
  KRX 전용 종목: 전일 15:20 KRX 가격 → 당일 09:03 KRX 가격

실행 모드(cron, 평일):
  --base-krx  15:20  당일 top-10 의 KRX 기준가 수집 → state 파일
  --base-nxt  19:50  당일 top-10 의 NXT 기준가 수집 (조회되는 종목 = NXT 종목으로 분류)
  --check-nxt 08:03  NXT 종목 갭 확정 → DB(gap_nxt_*) 저장. 알림 없음.
  --check-krx 09:03  KRX 종목 갭 확정(+ 08:03 실패분 NXT 재시도) → DB(gap_krx_*) 저장
                     → 텔레그램 알림은 여기서 하루 한 번만 전송.

기준가가 없으면(기준가 워커 미실행·마감 후 순위 진입 종목) 리포트 시점 가격으로
폴백하고 알림에 * 로 표시한다. 이때 NXT/KRX 분류는 08:03 NXT 조회 성공 여부로 대신한다.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
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

TOP_N = 10


def _most_recent_prior_date() -> str | None:
    dates = get_stock_report_dates(limit=5)
    today = datetime.now().date().isoformat()
    return next((d for d in dates if d < today), None)


def _load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception as e:
        logger.warning(f"state 파일 로드 실패: {e}")
        return None


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def _state_for(report_date: str) -> dict:
    """report_date 가 일치하는 state 만 신뢰한다(형식이 다르거나 다른 날짜면 초기화)."""
    state = _load_state()
    if (
        state
        and state.get("report_date") == report_date
        and isinstance(state.get("base"), dict)
    ):
        return state
    return {"report_date": report_date, "base": {}}


def _fetch_price(api: KiwoomRestClient, code: str, nxt: bool) -> int:
    """현재가 조회. 실패/무거래는 0. code 는 접미사 없는 종목코드."""
    stk_cd = code + ("_NX" if nxt else "")
    try:
        info = api.get_stock_basic_info(stk_cd)
        return abs(AnalysisEngine.parse_price(info.get("cur_prc", "0")))
    except Exception as e:
        logger.warning(f"현재가 조회 실패 [{stk_cd}]: {e}")
        return 0


def _row_meta(r: dict) -> dict:
    return {
        "rank": r["rank_no"],
        "name": r["stock_name"],
        "code": r["stock_code"].split(".")[0],
        "score": int(r.get("score") or 0),
    }


def _gap_row(r: dict, venue: str, base_price: int, now_price: int, approx: bool) -> dict:
    pct = (now_price - base_price) / base_price * 100
    return {
        **_row_meta(r),
        "venue": venue,
        "base_price": base_price,
        "now_price": now_price,
        "pct": pct,
        "approx": approx,
    }


def _fallback_base(r: dict) -> int:
    """기준가 미수집 시 리포트 시점 가격(current_price)으로 폴백."""
    return abs(int(r.get("current_price") or 0))


def _db_rows(rows: list[dict]) -> list[dict]:
    """확정 갭 행을 save_gap_check_results 입력 형태(venue별 키)로 변환."""
    out = []
    for x in rows:
        if "pct" not in x:
            continue
        key = "nxt" if x["venue"] == "NXT" else "krx"
        out.append({
            "rank": x["rank"],
            f"{key}_price": x["now_price"],
            f"{key}_pct": x["pct"],
        })
    return out


# ── 기준가 수집 (15:20 KRX / 19:50 NXT) ──

def run_base(venue: str):
    """당일 top-10 의 venue 기준가를 state 에 저장. venue: 'krx' | 'nxt'"""
    today = datetime.now().date().isoformat()
    reports = get_stock_reports_by_date(today)[:TOP_N]
    if not reports:
        logger.info(f"{today} 리포트 없음 — 종료")
        return

    state = _state_for(today)
    api = KiwoomRestClient()
    api.ensure_token()

    key = f"{venue}_price"
    got = 0
    for r in reports:
        code = r["stock_code"].split(".")[0]
        price = _fetch_price(api, code, nxt=(venue == "nxt"))
        if price > 0:
            state["base"].setdefault(code, {})[key] = price
            got += 1
    _save_state(state)
    logger.info(f"{venue.upper()} 기준가 수집 {got}/{len(reports)}건 ({today})")


# ── 갭 확정 (08:03 NXT / 09:03 KRX) ──

def run_check_nxt():
    """NXT 종목의 '전일 19:50 → 08:03' 갭 확정. DB 저장만, 알림 없음."""
    logger.info("=" * 60)
    logger.info("갭 체크 (NXT 08:03) 시작")
    logger.info("=" * 60)

    report_date = _most_recent_prior_date()
    if not report_date:
        logger.info("전날 리포트 없음 — 종료")
        return
    reports = get_stock_reports_by_date(report_date)[:TOP_N]
    if not reports:
        logger.info(f"{report_date} 리포트 데이터 없음 — 종료")
        return

    state = _state_for(report_date)
    base = state["base"]
    have_base = bool(base)
    if not have_base:
        logger.warning("기준가 미수집 — 리포트 시점 가격 폴백 + 08:03 NXT 조회로 venue 분류")

    api = KiwoomRestClient()
    api.ensure_token()

    rows = []
    for r in reports:
        code = r["stock_code"].split(".")[0]
        nxt_base = base.get(code, {}).get("nxt_price") or 0

        # NXT 종목 판정: 19:50 NXT 기준가가 있는 종목.
        # 기준가가 아예 없는 날(폴백)은 지금 NXT 조회가 되는 종목을 NXT 로 간주.
        if have_base and not nxt_base:
            continue  # KRX 종목 — 09:03 에 처리

        now_price = _fetch_price(api, code, nxt=True)
        if now_price <= 0:
            if have_base:
                # NXT 종목인데 조회 실패 → 09:03 에 NXT 재시도
                rows.append({**_row_meta(r), "venue": "NXT", "pending": True})
            continue

        base_price = nxt_base or _fallback_base(r)
        if base_price <= 0:
            rows.append({**_row_meta(r), "venue": "NXT", "error": True})
            continue
        rows.append(_gap_row(r, "NXT", base_price, now_price, approx=not nxt_base))

    try:
        save_gap_check_results(report_date, _db_rows(rows))
    except Exception as e:
        logger.warning(f"갭 체크 결과 DB 저장 실패: {e}")

    state["nxt_results"] = rows
    _save_state(state)
    done = sum(1 for x in rows if "pct" in x)
    logger.info(f"NXT 갭 확정 {done}건 / 대기 {len(rows) - done}건")


def run_check_krx():
    """KRX 종목의 '전일 15:20 → 09:03' 갭 확정 + NXT 실패분 재시도.
    전체 결과를 합쳐 DB 저장 후 텔레그램 알림을 하루 한 번 전송한다."""
    logger.info("=" * 60)
    logger.info("갭 체크 (KRX 09:03) 시작")
    logger.info("=" * 60)

    report_date = _most_recent_prior_date()
    if not report_date:
        logger.info("전날 리포트 없음 — 종료")
        return
    reports = get_stock_reports_by_date(report_date)[:TOP_N]
    if not reports:
        logger.info(f"{report_date} 리포트 데이터 없음 — 종료")
        return

    state = _state_for(report_date)
    base = state["base"]
    nxt_by_code = {
        x["code"]: x for x in state.get("nxt_results", []) if x.get("code")
    }

    api = KiwoomRestClient()
    api.ensure_token()

    final = []
    for r in reports:
        code = r["stock_code"].split(".")[0]
        prev = nxt_by_code.get(code)

        # 08:03 에 확정된 NXT 종목은 그대로 사용
        if prev and "pct" in prev:
            final.append(prev)
            continue

        # 08:03 조회 실패한 NXT 종목 → NXT 재시도 (창은 흐트러지지만 유실보다 낫다)
        if prev and prev.get("pending"):
            now_price = _fetch_price(api, code, nxt=True)
            nxt_base = base.get(code, {}).get("nxt_price") or 0
            base_price = nxt_base or _fallback_base(r)
            if now_price > 0 and base_price > 0:
                final.append(_gap_row(r, "NXT", base_price, now_price, approx=not nxt_base))
            else:
                final.append({**_row_meta(r), "venue": "NXT", "error": True})
            continue

        # KRX 종목
        krx_base = base.get(code, {}).get("krx_price") or 0
        base_price = krx_base or _fallback_base(r)
        now_price = _fetch_price(api, code, nxt=False)
        if now_price <= 0 or base_price <= 0:
            final.append({**_row_meta(r), "venue": "KRX", "error": True})
            continue
        final.append(_gap_row(r, "KRX", base_price, now_price, approx=not krx_base))

    try:
        save_gap_check_results(report_date, _db_rows(final))
    except Exception as e:
        logger.warning(f"갭 체크 결과 DB 저장 실패: {e}")

    check_time = datetime.now().strftime("%m-%d %H:%M")
    send_gap_check_alert(report_date, check_time, final)
    STATE_FILE.unlink(missing_ok=True)
    logger.info("갭 체크 완료 (알림 전송)")


if __name__ == "__main__":
    from core.market_calendar import exit_if_outside_window
    # cron: --base-krx 20 15 / --base-nxt 50 19 / --check-nxt 3 8 / --check-krx 3 9 (평일)
    # 휴장일·해당 시간대 밖(pm2 수동 재기동 등)이면 종료.
    if "--base-krx" in sys.argv:
        exit_if_outside_window(15, 15)
        run_base("krx")
    elif "--base-nxt" in sys.argv:
        exit_if_outside_window(19, 19)
        run_base("nxt")
    elif "--check-krx" in sys.argv or "--retry" in sys.argv:
        exit_if_outside_window(9, 9)
        run_check_krx()
    else:
        exit_if_outside_window(8, 8)
        run_check_nxt()
