"""갭상승 체크 워커 — 실매매 청산 창(venue별)에 맞춘 갭 측정

측정 창 (실제 종가베팅 매수→청산 시각과 일치):
  NXT 상장 종목: 전일 19:50 NXT 가격 → 당일 08:03 NXT 가격
  KRX 전용 종목: 전일 15:20 KRX 가격 → 당일 09:03 KRX 가격

실행 모드(cron, 평일):
  --base-krx  15:20  당일 top-10 의 KRX 기준가 수집 → state 파일
  --base-nxt  19:50  당일 유니버스 전체의 KRX 확정 종가 + NXT 기준가 수집.
                     → state 파일(top-10 갭 체크용, 기존 동작 불변)
                     → daily_stock_report NXT 스냅샷 UPDATE(엣지 연구용, F3의 눈)
                     → market_snapshot 1행 upsert(F2·레짐 연구용)
  --check-nxt 08:03  NXT 종목 갭 확정 → DB(gap_nxt_*) 저장. 알림 없음. (실매매 경로, top-10)
  --check-krx 09:03  KRX 종목 갭 확정(+ 08:03 실패분 NXT 재시도) → DB(gap_krx_*) 저장
                     → 텔레그램 알림은 여기서 하루 한 번만 전송.
  --label-nxt 08:06  [엣지 연구] 전일 유니버스 전체 NXT 상장 종목의 08:06 프리마켓 라벨
                     (nxt_open_price·nxt_open_ret, 앵커=KRX 확정 종가). 실매매 08:03 경로와
                     시각·부하 완전 분리(3분 늦어도 되는 가벼운 별도 패스). 알림 없음.

기준가가 없으면(기준가 워커 미실행·마감 후 순위 진입 종목) 리포트 시점 가격으로
폴백하고 알림에 * 로 표시한다. 이때 NXT/KRX 분류는 08:03 NXT 조회 성공 여부로 대신한다.

권리락(무상증자)일 종목은 기준가를 배정비율로 조정해 측정한다 — 아래 _ex_rights_ratio 주석.
"""
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from core.logging_setup import setup_logging
from core.kiwoom_client import KiwoomRestClient
from core.trading_engine import AnalysisEngine
from core.daily_ohlc import SANE_RET_PCT, build_ohlc_by_date
from core.repository.stock_report import (
    get_stock_report_dates,
    get_stock_reports_by_date,
    save_gap_check_results,
    save_nxt_snapshot,
    save_nxt_open_labels,
)
from core.repository.market_snapshot import save_market_snapshot
from core.repository.ex_rights import get_tickers_on
from core.market_data import fetch_edge_market_snapshot
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


def _fetch_price_qty(api: KiwoomRestClient, code: str, nxt: bool) -> tuple[int, int]:
    """현재가 + 누적 거래량 조회. 실패/무거래는 (0, 0). code 는 접미사 없는 종목코드.

    ka10001 은 거래대금 필드가 없어 거래대금은 호출부에서 거래량×현재가로 근사한다.
    """
    stk_cd = code + ("_NX" if nxt else "")
    try:
        info = api.get_stock_basic_info(stk_cd)
        price = abs(AnalysisEngine.parse_price(info.get("cur_prc", "0")))
        qty = abs(AnalysisEngine.parse_price(info.get("trde_qty", "0")))
        return price, qty
    except Exception as e:
        logger.warning(f"현재가/거래량 조회 실패 [{stk_cd}]: {e}")
        return 0, 0


def _row_meta(r: dict) -> dict:
    return {
        "rank": r["rank_no"],
        "name": r["stock_name"],
        "code": r["stock_code"].split(".")[0],
        "score": int(r.get("score") or 0),
        # 알림 정렬 1차 기준(화면 목록과 같은 순서). 표시는 하지 않는다.
        "rules": len([x for x in (r.get("rule_names") or "").split(",") if x]),
    }


# ── 권리락 조정 ──
# 무상증자 권리락일 아침 시세는 배정비율만큼 낮춰진 **권리락 기준가** 위에서 형성되는데, 갭 체크의
# 기준가는 전일 실거래가(19:50 NXT / 15:20 KRX)다. 그대로 재면 배정비율이 그대로 갭하락으로 찍힌다.
#   (조정 없이 재면 상승한 날이 두 자릿수 갭하락으로 찍힌다 — 실측 사례:
#   docs/history/infra-incidents.md)
# 그래서 기준가를 `전일가 / (1 + 1주당 신주 배정 주수)` 로 되돌린다(sql/50).
# 배정비율은 ex_rights_schedule(sql/48) — source='dart' 행이면 DART 확정값이다.
# 비율을 모르는 추정 행(source='inferred', ratio NULL)은 **손대지 않는다**: 그 행은 권리락일 자체가
# 불확실해 공시일 +1·+2영업일을 둘 다 등록한 것이라, 잘못 조정하면 정상 종목의 갭을 망친다.


def _ex_rights_today() -> dict[str, dict]:
    """오늘(=갭 확정일) 권리락 종목 맵. 조회 실패는 {} — 무조정으로 진행(종전 동작)."""
    try:
        return get_tickers_on(datetime.now().date().isoformat())
    except Exception as e:
        logger.warning(f"권리락 캘린더 조회 실패 — 무조정 진행: {e}")
        return {}


def _ex_rights_ratio(ex: dict | None) -> float | None:
    """조정에 쓸 배정비율. 권리락 아님·비율 미확정이면 None."""
    if not ex:
        return None
    ratio = float(ex.get("ratio") or 0)
    return ratio if ratio > 0 else None


def _gap_row(
    r: dict, venue: str, base_price: int, now_price: int, approx: bool,
    ex: dict | None = None,
) -> dict:
    ratio = _ex_rights_ratio(ex)
    if ratio:
        adj = round(base_price / (1 + ratio))
        logger.info(
            f"[{r['stock_name']}] 권리락 조정(배정비율 {ratio}) — 기준가 {base_price:,} → {adj:,}"
        )
        base_price = adj
    elif ex:
        logger.warning(
            f"[{r['stock_name']}] 권리락일이나 배정비율 미확정(추정 행) — 갭 무조정"
        )
    pct = (now_price - base_price) / base_price * 100
    return {
        **_row_meta(r),
        "venue": venue,
        "base_price": base_price,
        "now_price": now_price,
        "pct": pct,
        "approx": approx,
        "ex_rights_ratio": ratio,
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
            "ex_rights_ratio": x.get("ex_rights_ratio"),
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


def run_market_snap():
    """market_snapshot 1행 upsert (F2 해외 동조·레짐의 눈).

    두 번 돈다 — **14:30**(매수 직전, `--market-snap`)과 **19:50**(`--base-nxt` 말미).
    14:30 회차를 넣은 이유: 예전엔 19:50 에만 구워서 선정 시점(13~15시·19:00 회차)엔 당일
    행이 아예 없었고, 그래서 `market.` 축을 쓰는 rule 은 통계와 무관하게 영구 승격 불가였다.

    ⚠️ 저장은 `_FIELDS` **전체 덮어쓰기**라 최종 저장값은 언제나 19:50 회차 값이다
    (= 채점이 보는 값). 그래서 선정 시점에 쓸 수 있는 축은 **두 시각 값이 같은 것뿐**이고,
    그 판정은 core/edge_policy.SELECTION_TIME_MARKET_COLS 가 갖는다(미국 정규장 확정치 2종).
    """
    today = datetime.now().date().isoformat()
    try:
        snap = fetch_edge_market_snapshot()
        save_market_snapshot({"snapshot_date": today, **snap})
        logger.info(f"market_snapshot 저장 완료 ({today})")
    except Exception as e:
        logger.warning(f"market_snapshot 저장 실패: {e}")


def run_base_nxt():
    """19:50 NXT 기준가 수집 (확장판) — 순수 관측·기록 레이어(매매 영향 0).

    대상은 당일 유니버스 전체(include_unselected=True). 종목당 API 2콜(KRX 확정 종가 +
    NXT 19:50 현재가, rate limit 안전권으로 콜마다 0.3s sleep).

    3곳에 기록한다:
      1) state 파일 — top-10 갭 체크용 NXT 기준가(기존 동작 불변. 전 유니버스를 담아도
         08:03/09:03 체크는 top-10 코드만 조회하므로 무해).
      2) daily_stock_report — krx_close_price·nxt_price_1950·nxt_gap_pct·nxt_after_value·
         nxt_listed UPDATE(리포트 행이 이미 존재 → upsert 아님, F3의 눈).
      3) market_snapshot — 당일 시장 지표 1행 upsert(F2·레짐의 눈).

    조회 실패 종목은 NULL 유지(그날 그 종목만 F3 평가 제외) — 파이프라인은 계속 진행.
    """
    today = datetime.now().date().isoformat()
    reports = get_stock_reports_by_date(today, include_unselected=True)
    if not reports:
        logger.info(f"{today} 리포트 없음 — 종료")
        return

    state = _state_for(today)
    api = KiwoomRestClient()
    api.ensure_token()

    snapshot_rows = []
    got = 0
    for r in reports:
        code = r["stock_code"].split(".")[0]
        krx_price, _ = _fetch_price_qty(api, code, nxt=False)
        time.sleep(0.3)
        nxt_price, nxt_qty = _fetch_price_qty(api, code, nxt=True)
        time.sleep(0.3)

        nxt_listed = 1 if nxt_price > 0 else 0
        nxt_gap_pct = None
        if nxt_listed and krx_price > 0:
            nxt_gap_pct = (nxt_price - krx_price) / krx_price * 100
        # ka10001 에 거래대금 필드가 없어 거래량×현재가로 근사(순수 애프터마켓 아닌 NXT 세션 전체).
        nxt_after_value = nxt_qty * nxt_price if (nxt_listed and nxt_qty > 0) else None

        # top-10 갭 체크용 NXT 기준가(기존 run_base('nxt') 와 동일 키).
        if nxt_price > 0:
            state["base"].setdefault(code, {})["nxt_price"] = nxt_price
            got += 1

        snapshot_rows.append({
            "stock_code": code,
            "krx_close_price": krx_price or None,
            "nxt_price_1950": nxt_price or None,
            "nxt_gap_pct": nxt_gap_pct,
            "nxt_after_value": nxt_after_value,
            "nxt_listed": nxt_listed,
        })

    _save_state(state)
    try:
        save_nxt_snapshot(today, snapshot_rows)
        logger.info(f"NXT 스냅샷 저장 {len(snapshot_rows)}건 (NXT 상장 {got}건, {today})")
    except Exception as e:
        logger.warning(f"NXT 스냅샷 DB 저장 실패: {e}")

    run_market_snap()


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

    ex_map = _ex_rights_today()
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
        rows.append(
            _gap_row(r, "NXT", base_price, now_price, approx=not nxt_base, ex=ex_map.get(code))
        )

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

    ex_map = _ex_rights_today()
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
                final.append(
                    _gap_row(r, "NXT", base_price, now_price,
                             approx=not nxt_base, ex=ex_map.get(code))
                )
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
        final.append(
            _gap_row(r, "KRX", base_price, now_price, approx=not krx_base, ex=ex_map.get(code))
        )

    try:
        save_gap_check_results(report_date, _db_rows(final))
    except Exception as e:
        logger.warning(f"갭 체크 결과 DB 저장 실패: {e}")

    check_time = datetime.now().strftime("%m-%d %H:%M")
    send_gap_check_alert(report_date, check_time, final)
    STATE_FILE.unlink(missing_ok=True)
    logger.info("갭 체크 완료 (알림 전송)")


# ── 엣지 연구용 프리마켓 라벨 (08:06 NXT, 유니버스 전체) ──
# 일봉 파싱·±35% 가드는 core.daily_ohlc 공유 모듈 — outcome_backfill 과 기준이 어긋나면
# exit_label 간 청산창 비교가 오염되므로 반드시 같은 모듈을 쓴다.


def _krx_close_from_chart(
    api: KiwoomRestClient, code: str, report_dt: str,
    cache: dict[str, dict[str, tuple[int, int, int, int]]],
) -> int:
    """수정주가 일봉에서 report_dt(YYYYMMDD) 종가 조회 — krx_close_price 미수집분 앵커 폴백.
    종목당 1회만 조회(캐시). 없으면 0."""
    if code not in cache:
        cache[code] = build_ohlc_by_date(api, code)
    bar = cache[code].get(report_dt)
    return bar[3] if bar else 0


def run_label_nxt():
    """08:06 유니버스 전체 NXT 프리마켓 라벨 수집 (nxt_open_price·nxt_open_ret).

    앵커는 전일 KRX 확정 종가(Phase 1 krx_close_price, 미수집 시 일봉 종가 폴백)로 통일한다.
    NXT 상장 종목(nxt_listed=1)만 조회 — 미상장은 라벨 없음(4종만). 실매매 08:03 경로(top-10)와
    시각·부하 완전 분리. 조회 실패는 NULL 유지(연구 표본만 감소, 매매 무영향).
    """
    logger.info("=" * 60)
    logger.info("NXT 프리마켓 라벨 (08:06) 시작")
    logger.info("=" * 60)

    report_date = _most_recent_prior_date()
    if not report_date:
        logger.info("전날 리포트 없음 — 종료")
        return
    reports = get_stock_reports_by_date(report_date, include_unselected=True)
    if not reports:
        logger.info(f"{report_date} 리포트 데이터 없음 — 종료")
        return

    api = KiwoomRestClient()
    api.ensure_token()

    report_dt = report_date.replace("-", "")
    close_cache: dict[str, dict[str, tuple[int, int, int, int]]] = {}
    rows = []
    listed = 0
    for r in reports:
        if not r.get("nxt_listed"):
            continue  # NXT 미상장 → 프리마켓 라벨 없음(일봉 4종만 보유)
        listed += 1
        code = r["stock_code"].split(".")[0]
        nxt_price = _fetch_price(api, code, nxt=True)
        time.sleep(0.3)
        if nxt_price <= 0:
            continue

        anchor = r.get("krx_close_price") or _krx_close_from_chart(api, code, report_dt, close_cache)
        if not anchor or anchor <= 0:
            continue
        ret = (nxt_price - anchor) / anchor * 100
        if abs(ret) > SANE_RET_PCT:
            logger.warning(f"비정상 등락 스킵 [{code}]: {ret:+.1f}% (분할/데이터 아티팩트 의심)")
            continue
        rows.append({
            "stock_code": r["stock_code"],
            "nxt_open_price": nxt_price,
            "nxt_open_ret": round(ret, 3),
        })

    try:
        save_nxt_open_labels(report_date, rows)
        logger.info(f"NXT 프리마켓 라벨 {len(rows)}/{listed}건 (NXT 상장 기준, {report_date})")
    except Exception as e:
        logger.warning(f"NXT 프리마켓 라벨 DB 저장 실패: {e}")


if __name__ == "__main__":
    from core.market_calendar import exit_if_outside_window
    # cron: --market-snap 30 14 / --base-krx 20 15 / --base-nxt 50 19 / --check-nxt 3 8 /
    #       --label-nxt 6 8 / --check-krx 3 9 (평일)
    # 휴장일·해당 시간대 밖(pm2 수동 재기동 등)이면 종료.
    if "--market-snap" in sys.argv:
        exit_if_outside_window(14, 14)
        run_market_snap()
    elif "--base-krx" in sys.argv:
        exit_if_outside_window(15, 15)
        run_base("krx")
    elif "--base-nxt" in sys.argv:
        exit_if_outside_window(19, 19)
        run_base_nxt()
    elif "--label-nxt" in sys.argv:
        exit_if_outside_window(8, 8)
        run_label_nxt()
    elif "--check-krx" in sys.argv or "--retry" in sys.argv:
        exit_if_outside_window(9, 9)
        run_check_krx()
    else:
        exit_if_outside_window(8, 8)
        run_check_nxt()
