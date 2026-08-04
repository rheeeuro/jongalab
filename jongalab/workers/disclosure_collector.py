"""DART 공시 수집 워커 — 당일 전자공시를 사건 계층(stock_event)에 멱등 적재한다.

[왜 필요한가]
종가베팅의 매수 창은 KRX 15:20 / NXT 19:50 인데, 익일 시초가를 가장 세게 움직이는
공시(유상증자·CB·공급계약·계약해지)는 장 마감 후 15:30~18:00 에 몰린다. 이 창을
아무도 보지 않아 "저녁에 안 사면 될 것을 사고 나서 아침에 news_guard 가 던지는" 구조였다.
이 워커가 그 구간을 채운다.

[흐름] 1사이클(단발 프로세스, 스케줄러가 30분마다 spawn)
  1. DART list.json 에서 오늘 접수분(유가+코스닥) 전체 페이지 조회
  2. report_nm 을 core.disclosure_events.classify 로 룰 분류(LLM 없음)
  3. stock_event 에 INSERT IGNORE — (source, source_key=접수번호) UNIQUE 로 재실행 멱등
  first_seen_at 은 **이번 수집 시각**을 쓴다: DART list API 가 접수 '시각'을 주지 않아,
  "선정 시점에 이 공시가 이미 있었는가"는 우리가 처음 본 시각으로 판정한다(±폴링주기).

[소비] closing_bet 이 선정 시점에 stock_event 를 읽어 daily_stock_report 의
  disc_count/disc_bad_type/disc_good_type 을 굽고, live veto rule(veto_disclosure_bad)이
  disc_bad_type 을 보고 후보에서 제외한다. 저녁 재실행(19:00)에서 제외된 종목은
  push_trade_signals 가 pending 시그널을 expired 로 정리하므로 19:30 NXT 매수에서 자동 탈락한다.

[실패 안전] 키 미설정·API 오류는 exit 0 로 조용히 끝낸다(수집 공백 = disc_* NULL =
  veto 미개입). 종가베팅 선정은 공시 수집 성패와 무관하게 그대로 돌아간다.

[cron] 평일 08:20~20:50 매 30분(:20/:50) — closing_bet(:00/:30) 직전에 갱신되도록 어긋나게 둔다.
단발 실행: uv run workers/disclosure_collector.py [--date YYYYMMDD]
"""
import argparse
import logging
from datetime import date, datetime, timedelta

from core.dart_client import (
    DOC_URL, DartError, bonus_issue_schedules, capital_increase_methods, is_configured,
    list_filings,
)
from core.disclosure_events import UNKNOWN_IC, classify, refine_capital_increase
from core.logging_setup import setup_logging
from core.market_calendar import next_trading_day, prev_trading_day
from core.repository import ex_rights as ex_rights_repo
from core.repository import stock_event as event_repo

setup_logging()
logger = logging.getLogger("DisclosureCollector")

SOURCE = "dart"


def _resolve_ic_methods(filings: list[dict]) -> dict[str, str]:
    """유상증자 건에 한해 증자방식(ic_mthn)을 접수번호별로 조회.

    보고서명이 '주요사항보고서(유상증자결정)' 하나뿐이라 주주배정(희석 악재)과 제3자배정
    (전략적 투자 유치 — 호재 가능)을 제목으로는 못 가른다. 유상증자 건이 있는 회사만
    piicDecsn 을 부르므로 추가 콜은 하루 10회 안쪽이다. 실패는 빈 값 = '미상' = veto 안 함.
    """
    targets: dict[tuple[str, str], None] = {}
    for f in filings:
        if classify(f.get("report_nm") or "")["event_type"] != UNKNOWN_IC:
            continue
        corp_code = (f.get("corp_code") or "").strip()
        rcept_dt = (f.get("rcept_dt") or "").strip()
        if corp_code and len(rcept_dt) == 8:
            targets[(corp_code, rcept_dt)] = None

    methods: dict[str, str] = {}
    for corp_code, rcept_dt in targets:
        methods.update(capital_increase_methods(corp_code, rcept_dt))
    if targets:
        logger.info("유상증자 방식 조회 %d개사 → %d건 확인", len(targets), len(methods))
    return methods


EX_RIGHTS_TRIGGERS = ("무상증자", "권리락")
# 권리락 공시가 트리거일 때 결정 공시를 얼마나 거슬러 찾을지(일). 무상증자 결정 → 권리락은
# 보통 2~3주라 넉넉히 잡는다(실측: 알테오젠 결정 7/20 → 권리락 8/5 = 16일).
EX_RIGHTS_LOOKBACK_DAYS = 120


def _resolve_ex_rights(filings: list[dict], date_yyyymmdd: str) -> list[dict]:
    """무상증자 건에 한해 **권리락 예정일**을 계산한다(sql/48 캘린더 행).

    트리거는 두 가지이고 조회는 하나다(fricDecsn):
      · `무상증자` 결정 공시 — 정상 경로(권리락 2~3주 전에 미리 채워진다)
      · `권리락` 공시 — 결정 공시를 놓친 종목의 보완 경로(수집 시작 전 결정분 등).
        권리락 1~2영업일 전에 오므로 NXT 19:30 매수는 막을 수 있다.
    권리락일 = 신주배정기준일(nstk_asstd) **직전 영업일**. 근거는 sql/48 주석(실측 3건).

    조회 실패·기준일 없음은 그 종목을 그냥 건너뛴다(미개입 — 캘린더에 없으면 매수는 정상 진행).
    """
    targets: dict[tuple[str, str], dict] = {}
    for f in filings:
        event_type = classify(f.get("report_nm") or "")["event_type"]
        if event_type not in EX_RIGHTS_TRIGGERS:
            continue
        corp_code = (f.get("corp_code") or "").strip()
        ticker = (f.get("stock_code") or "").strip()
        rcept_no = (f.get("rcept_no") or "").strip()
        if not (corp_code and ticker and rcept_no):
            continue
        # 권리락 공시가 트리거면 폴백(추정) 자격이 있다 — 그 공시 자체가 "곧 권리락"의 증거다.
        # 무상증자 결정 공시만 본 경우엔 추정하지 않는다(기준일이 없으면 아직 일정 미확정).
        prev = targets.get((corp_code, ticker)) or {}
        targets[(corp_code, ticker)] = {
            "corp_name": (f.get("corp_name") or "").strip() or prev.get("corp_name"),
            "rcept_no": rcept_no,
            "ex_notice": prev.get("ex_notice") or event_type == "권리락",
        }

    if not targets:
        return []

    end_de = date_yyyymmdd
    disc_date = datetime.strptime(date_yyyymmdd, "%Y%m%d").date()
    bgn_dt = disc_date - timedelta(days=EX_RIGHTS_LOOKBACK_DAYS)
    rows, inferred = [], 0
    for (corp_code, ticker), meta in targets.items():
        found = bonus_issue_schedules(corp_code, bgn_dt.strftime("%Y%m%d"), end_de)
        for s in found:
            record = date.fromisoformat(s["record_date"])
            rows.append({
                "ticker": ticker,
                "ex_rights_date": prev_trading_day(record).isoformat(),
                "record_date": s["record_date"],
                "ratio": s.get("ratio"),
                "listing_date": s.get("listing_date"),
                "source": "dart",
                "source_key": s["rcept_no"],
                "corp_name": s.get("corp_name") or meta.get("corp_name"),
            })
        if found or not meta["ex_notice"]:
            continue
        # 폴백 — 기준일을 못 얻었지만 권리락 공시는 왔다(자율공시 건 등, sql/48 주석).
        # 공시일 직후 2영업일을 권리락 가능일로 추정 등록해 과잉 차단 쪽으로 기운다.
        nxt = next_trading_day(disc_date)
        for d in (nxt, next_trading_day(nxt)):
            rows.append({
                "ticker": ticker, "ex_rights_date": d.isoformat(), "record_date": None,
                "ratio": None, "listing_date": None, "source": "inferred",
                "source_key": meta["rcept_no"], "corp_name": meta.get("corp_name"),
            })
        inferred += 1
    logger.info("무상증자 일정 조회 %d개사 → 권리락 예정 %d건(기준일 확정 %d / 추정 %d개사)",
                len(targets), len(rows), len(rows) - inferred * 2, inferred)
    return rows


def _to_rows(filings: list[dict], seen_at: datetime) -> list[dict]:
    """DART 원본 항목 → stock_event 행. 분류 실패 항목은 건너뛴다(수집은 계속)."""
    ic_methods = _resolve_ic_methods(filings)
    rows = []
    for f in filings:
        rcept_no = (f.get("rcept_no") or "").strip()
        ticker = (f.get("stock_code") or "").strip()
        report_nm = (f.get("report_nm") or "").strip()
        rcept_dt = (f.get("rcept_dt") or "").strip()
        if not (rcept_no and ticker and report_nm and len(rcept_dt) == 8):
            continue
        c = refine_capital_increase(classify(report_nm), ic_methods.get(rcept_no))
        rows.append({
            "ticker": ticker,
            "event_date": f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}",
            "source": SOURCE,
            "source_key": rcept_no,
            "event_type": c["event_type"],
            "direction": c["direction"],
            "is_veto_type": c["is_veto_type"],
            "is_subject": c["is_subject"],
            "is_correction": c["is_correction"],
            "first_seen_at": seen_at,
            "title": report_nm[:255],
            "corp_name": (f.get("corp_name") or "")[:80] or None,
            "raw_url": DOC_URL.format(rcept_no=rcept_no),
        })
    return rows


def _seen_at(date_yyyymmdd: str, now: datetime) -> datetime:
    """first_seen_at 값 결정.

    실시간 수집(오늘)은 지금 시각 = 진짜 최초 관측 시각.
    과거 백필은 관측 시각을 알 수 없다 — '오늘 지금'을 넣으면 그 공시가 마치 오늘 나온 것처럼
    보여 창(장중/장마감후) 분석을 오염시킨다. 그래서 **그날 00:00 을 센티넬로** 쓴다:
    수집기는 08:20~20:50 에만 도니 00:00 은 실관측일 수 없어, 백필분을 나중에 구분할 수 있다.
    """
    if date_yyyymmdd == now.strftime("%Y%m%d"):
        return now
    return datetime.strptime(date_yyyymmdd, "%Y%m%d")


def run(date_yyyymmdd: str) -> int:
    if not is_configured():
        logger.info("DART_API_KEY 미설정 — 공시 수집 건너뜀(.env 에 키 추가 필요)")
        return 0

    try:
        filings = list_filings(date_yyyymmdd)
    except DartError as e:
        logger.error("DART 조회 실패 — 이번 주기 건너뜀(다음 주기 재시도): %s", e)
        return 0

    now = datetime.now()
    seen_at = _seen_at(date_yyyymmdd, now)
    if seen_at != now:
        logger.info("백필 모드 %s — first_seen_at 은 00:00 센티넬(실관측 시각 아님)", date_yyyymmdd)
    rows = _to_rows(filings, seen_at)
    if not rows:
        logger.info("%s 상장사 공시 없음(조회 %d건)", date_yyyymmdd, len(filings))
        return 0

    try:
        inserted = event_repo.save_events(rows)
        total = event_repo.count_by_date(rows[0]["event_date"])
    except Exception as e:
        logger.error("stock_event 적재 실패: %s", e)
        return 1

    # 권리락 예정일 캘린더(sql/48) — trading 이 익일 권리락 종목 매수를 건너뛴다.
    # 공시 적재와 독립: 실패해도 수집 결과를 되돌리지 않는다(캘린더가 비면 매수는 정상 진행).
    try:
        ex_rows = _resolve_ex_rights(filings, date_yyyymmdd)
        if ex_rows:
            new_ex = ex_rights_repo.save_schedules(ex_rows)
            logger.info("권리락 예정 적재 — 신규 %d건 / 조회 %d건: %s", new_ex, len(ex_rows),
                        ", ".join(f"{r['corp_name']}({r['ticker']}) {r['ex_rights_date']}"
                                  f"×{r['ratio']}" for r in ex_rows[:10]))
    except Exception as e:
        logger.warning("권리락 예정 적재 실패(공시 수집은 정상 완료): %s", e)

    bad = [r for r in rows if r["is_veto_type"] and not r["is_correction"]]
    logger.info("공시 수집 %s — 조회 %d건 / 신규 %d건 / 당일 누적 %d건",
                date_yyyymmdd, len(rows), inserted, total)
    if bad:
        logger.info("veto 대상 악재 공시 %d건: %s", len(bad),
                    ", ".join(f"{r['corp_name']}({r['ticker']}) {r['event_type']}"
                              for r in bad[:10]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DART 공시 수집 워커")
    parser.add_argument("--date", help="수집 일자 YYYYMMDD (기본: 오늘)")
    args = parser.parse_args()
    return run(args.date or datetime.now().strftime("%Y%m%d"))


if __name__ == "__main__":
    import sys

    from core.market_calendar import exit_if_not_trading_day

    # 휴장일엔 상장사 공시가 거의 없고 종가베팅도 안 도므로 수집하지 않는다.
    # --date 로 과거분을 수동 백필할 땐 거래일 가드를 건너뛴다.
    if "--date" not in sys.argv:
        exit_if_not_trading_day()
    sys.exit(main())
