"""market_snapshot 관측 슬롯 소급 백필 — 일봉으로 복원 가능한 축만 채운다 (단발 실행).

시황 축은 하루에 표본 1개라 종목 축보다 수십 배 느리게 쌓인다. 실측 기록은 2026-07-06 부터인데
채점 라벨(daily_stock_report.next_open_ret)은 그보다 훨씬 앞부터 있어, 그 간극이 시황 축을
검정 불가로 만든다. 일봉으로 되살릴 수 있는 축은 되살려 표본을 늘리는 것이 이 워커의 목적이다.

**복원 가능한 축만 넣는다.** 판정 기준은 "그 값이 일봉 종가로 재현되는가"이고, 겹치는 구간에서
실측값과 대조해 확인한다(--verify 로 언제든 재확인):
  · 전 미국 세션 확정치 — spx_ret · sox_ret · ewy_ret · koru_ret · skhy_ret
  · 당일 한국 종가       — kospi_ret · kosdaq_ret
제외: nq_fut_ret · vix · usdkrw_ret · wti_ret 은 한국 오후에 **이미 진행 중인 봉**의 스냅샷이라
      지나가면 복원할 수 없다. k200f_* · news_* · ah_* 는 자체 수집분이라 외부 일봉에 없다.

**두 슬롯에 적재한다** — 슬롯마다 넣을 수 있는 축이 다르다:
  · 관측 슬롯(1950): 위 전체. 그 시각 한국장이 끝나 있으므로 지수 종가도 유효하다.
  · rule 축(1430)  : **미국 확정치 5종만**. 미국장은 한국시간 06:00 에 끝나 14:30 에도 같은 값이
    라는 게 증명되므로 소급 복원이 정당하다. 한국 지수는 14:30 엔 장중이라 종가를 넣으면
    **미래 정보**가 되므로 절대 넣지 않는다.
source 는 'backfill'(신규 행)이고, 실측 행의 빈 칸을 메우면 그 행은 **'mixed'** 가 된다 —
한 행에 실측과 복원이 섞였다는 표시다. --verify 는 순수 'live' 행만 대조한다(복원값을 복원값과
대조하면 검증이 순환한다).

sox_ret 은 수집 결함 이력이 있어 **항상 세 심볼(^SOX·SOXX·SMH) 교차검증**을 통과한 값만 쓴다.

실행:
  uv run workers/market_snapshot_backfill.py --verify           # 겹치는 구간 대조만(쓰기 없음)
  uv run workers/market_snapshot_backfill.py --dry-run          # 채울 행 미리보기
  uv run workers/market_snapshot_backfill.py --apply            # 적재
  uv run workers/market_snapshot_backfill.py --repair-sox       # 결함 sox_ret 정정(교차검증 필수)
"""
import argparse
import logging
import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")

from core.db import get_db
from core.logging_setup import setup_logging
from core.repository.market_snapshot import SLOT_KRX, SLOT_OBS

setup_logging()
logger = logging.getLogger("MarketSnapshotBackfill")

# 복원 대상 — {컬럼: (yfinance 심볼, 정렬)}
#   prev_us : snapshot_date 이전 마지막 거래일 봉의 등락률(미국 정규장은 한국시간 06:00 마감)
#   same_kr : snapshot_date 당일 봉의 등락률(한국 지수는 그날 종가)
RESTORABLE: dict[str, tuple[str, str]] = {
    "spx_ret": ("^GSPC", "prev_us"),
    "sox_ret": ("^SOX", "prev_us"),
    "ewy_ret": ("EWY", "prev_us"),
    "koru_ret": ("KORU", "prev_us"),
    "skhy_ret": ("SKHY", "prev_us"),
    "kospi_ret": ("^KS11", "same_kr"),
    "kosdaq_ret": ("^KQ11", "same_kr"),
}

# rule 축(1430)에도 넣을 수 있는 축 — 미국 정규장이 한국시간 06:00 에 끝나 그날 안에는 더
# 변하지 않는 값들. 한국 지수는 14:30 엔 장중이라 여기 들어가면 미래 정보가 된다.
SLOT_INVARIANT: frozenset[str] = frozenset({"spx_ret", "sox_ret", "ewy_ret", "koru_ret", "skhy_ret"})

# 교차검증이 필요한 축 — 수집 결함 이력이 있어 대체 심볼과 대조한 값만 쓴다.
CROSS_CHECKED: frozenset[str] = frozenset({"sox_ret"})

# 실측값과 복원값이 같다고 볼 허용 오차(%p). 실측 저장이 소수 2자리 반올림이라 그 폭.
TOL = 0.05

# sox_ret 정정 시 교차검증에 쓰는 대체 심볼 — 셋이 같은 방향·크기여야 그 세션 값을 신뢰한다.
_SOX_CROSS = ("^SOX", "SOXX", "SMH")
_SOX_CROSS_TOL = 1.5  # ETF 와 지수는 구성이 달라 %p 차이를 이 폭까지 허용


def _bars(symbol: str, start: date, end: date) -> list[tuple[date, float]]:
    """일봉 종가 [(날짜, 종가)] — 실패·빈 응답은 빈 리스트."""
    import yfinance as yf
    try:
        df = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(),
                                       interval="1d", auto_adjust=False)
    except Exception as e:
        logger.warning("%s 일봉 조회 실패: %s", symbol, e)
        return []
    if df is None or df.empty or "Close" not in df:
        logger.warning("%s 일봉 빈 응답", symbol)
        return []
    closes = df["Close"].dropna()
    return [(d.date(), float(v)) for d, v in zip(closes.index, closes.values)]


def _pct_at(bars: list[tuple[date, float]], target: date, align: str) -> float | None:
    """정렬 규칙에 따라 target 에 대응하는 봉의 전일대비 등락률(%)."""
    if not bars:
        return None
    if align == "same_kr":
        idx = next((i for i, (d, _) in enumerate(bars) if d == target), None)
    else:
        prior = [i for i, (d, _) in enumerate(bars) if d < target]
        idx = prior[-1] if prior else None
    if idx is None or idx < 1:
        return None
    prev = bars[idx - 1][1]
    if not prev:
        return None
    return round((bars[idx][1] - prev) / prev * 100, 2)


def _cross_ok(bars: dict[str, list], target: date, base: float) -> bool:
    """대체 심볼들이 같은 세션에서 base 와 비슷한 등락을 보이는가(구성 차이만큼 허용)."""
    peers = [_pct_at(bars[s], target, "prev_us") for s in _SOX_CROSS if s != "^SOX"]
    peers = [v for v in peers if v is not None]
    return bool(peers) and all(abs(base - v) <= _SOX_CROSS_TOL for v in peers)


def _restore(bars: dict[str, list], col: str, target: date) -> float | None:
    """한 컬럼의 복원값 — 교차검증 대상 축은 통과해야 값을 준다."""
    sym, align = RESTORABLE[col]
    v = _pct_at(bars[sym], target, align)
    if v is None:
        return None
    if col in CROSS_CHECKED and not _cross_ok(bars, target, v):
        logger.warning("%s %s 교차검증 미통과 → 건너뜀", target, col)
        return None
    return v


def _report_dates() -> list[date]:
    """채점 라벨이 있는 리포트 날짜 — 백필 대상 구간의 정의.

    **오늘은 제외한다** — 세션이 아직 안 끝났으면 일봉이 진행 중인 봉이라 복원값이 종가가
    아니다(당일 행은 그날 수집 잡이 실측으로 채운다).
    """
    today = date.today()
    with get_db() as (conn, cursor):
        cursor.execute("SELECT DISTINCT report_date FROM daily_stock_report ORDER BY report_date")
        return [r["report_date"] for r in cursor.fetchall() if r["report_date"] < today]


def _existing(slot: str = SLOT_OBS) -> dict[date, dict]:
    """그 슬롯의 현재 행 {날짜: row}."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM market_snapshot WHERE slot = %s", (slot,))
        return {r["snapshot_date"]: r for r in cursor.fetchall()}


def _load_bars(dates: list[date], symbols: list[str]) -> dict[str, list]:
    start, end = dates[0] - timedelta(days=14), dates[-1] + timedelta(days=3)
    return {sym: _bars(sym, start, end) for sym in symbols}


def verify(dates: list[date], rows: dict[date, dict]) -> dict[str, bool]:
    """겹치는 구간에서 복원값 vs 실측값 대조. 반환 {컬럼: 통과 여부}.

    한 컬럼이라도 어긋나면 그 컬럼은 백필하지 않는다 — 복원 정의가 실측 정의와 다르다는 뜻이고,
    그대로 넣으면 같은 컬럼에 두 정의가 섞여 채점이 오염된다.
    """
    bars = _load_bars(dates, [s for s, _ in RESTORABLE.values()] + list(_SOX_CROSS))
    verdict: dict[str, bool] = {}
    logger.info("%-11s %5s %5s %9s %9s  판정", "컬럼", "대조", "일치", "평균|차|", "최대|차|")
    for col in RESTORABLE:
        diffs = []
        for d, row in sorted(rows.items()):
            got = row.get(col)
            if got is None or (row.get("source") or "live") != "live":
                continue
            val = _restore(bars, col, d)
            if val is None:
                continue
            diffs.append(abs(float(got) - val))
        if not diffs:
            verdict[col] = False
            logger.warning("%-11s %5d %5s %9s %9s  대조 표본 없음 → 백필 제외", col, 0, "-", "-", "-")
            continue
        hit = sum(1 for x in diffs if x <= TOL)
        ok = hit == len(diffs)
        verdict[col] = ok
        logger.info("%-11s %5d %5d %9.3f %9.3f  %s", col, len(diffs), hit,
                    sum(diffs) / len(diffs), max(diffs),
                    "✅ 복원 가능" if ok else "❌ 불일치 → 백필 제외")
    return verdict


def backfill(dates: list[date], rows: dict[date, dict], cols: list[str], apply: bool) -> None:
    """슬롯별로 비어 있는 날짜·컬럼만 채운다. 기존 값은 절대 덮지 않는다."""
    bars = _load_bars(dates, [RESTORABLE[c][0] for c in cols] + list(_SOX_CROSS))
    plan = [(SLOT_OBS, cols), (SLOT_KRX, [c for c in cols if c in SLOT_INVARIANT])]
    for slot, slot_cols in plan:
        if not slot_cols:
            continue
        existing = rows if slot == SLOT_OBS else _existing(slot)
        inserts = updates = filled = 0
        for d in dates:
            row = existing.get(d)
            vals = {}
            for col in slot_cols:
                if row is not None and row.get(col) is not None:
                    continue  # 기존 값 보존
                v = _restore(bars, col, d)
                if v is not None:
                    vals[col] = v
            if not vals:
                continue
            filled += len(vals)
            if row is None:
                inserts += 1
            else:
                updates += 1
            if not apply:
                continue
            with get_db() as (conn, cursor):
                if row is None:
                    cursor.execute(
                        f"INSERT INTO market_snapshot (snapshot_date, slot, source, "
                        f"{', '.join(vals)}) VALUES (%s, %s, 'backfill', "
                        f"{', '.join(['%s'] * len(vals))})",
                        (d, slot, *vals.values()),
                    )
                else:
                    # 실측 행에 복원값이 섞이면 'mixed' — 그 행은 더 이상 검증 기준이 아니다.
                    sets = ", ".join(f"{c} = %s" for c in vals)
                    src = "mixed" if (row.get("source") or "live") == "live" else row["source"]
                    cursor.execute(
                        f"UPDATE market_snapshot SET {sets}, source = %s "
                        f"WHERE snapshot_date = %s AND slot = %s",
                        (*vals.values(), src, d, slot),
                    )
                conn.commit()
        verb = "적재" if apply else "적재 예정(dry-run)"
        logger.info("슬롯 %s %s — 신규 행 %d · 기존 행 보강 %d · 값 %d개 (컬럼 %s)",
                    slot, verb, inserts, updates, filled, ",".join(slot_cols))


def repair_sox(rows: dict[date, dict], apply: bool) -> None:
    """결함 sox_ret 정정 — 세 심볼 교차검증을 통과한 세션 값만 쓴다.

    수집 시점 yfinance 가 최근 봉을 빠뜨리면 며칠 전 세션 등락률이 당일 값으로 저장된다
    (수집 가드는 core/market_data._drop_stale_us_bars 가 담당, 경위는 docs/history).
    이미 저장된 결함 값은 소급 정정이 필요하다. 정정 대상은 **복원값과 어긋나는 행**뿐이다.
    """
    dates = sorted(rows)
    if not dates:
        return
    bars = _load_bars(dates, list(_SOX_CROSS))
    fixed = skipped = 0
    for d in dates:
        got = rows[d].get("sox_ret")
        if got is None:
            continue
        cross = {sym: _pct_at(bars[sym], d, "prev_us") for sym in _SOX_CROSS}
        base = cross["^SOX"]
        if base is None:
            continue
        if abs(float(got) - base) <= TOL:
            continue  # 정상
        peers = [v for s, v in cross.items() if s != "^SOX" and v is not None]
        if not peers or any(abs(base - v) > _SOX_CROSS_TOL for v in peers):
            logger.warning("%s sox_ret 저장 %+.2f vs 복원 %+.2f — 교차검증 미통과(%s) → 건너뜀",
                           d, float(got), base,
                           ", ".join(f"{s}{v:+.2f}" for s, v in cross.items() if v is not None))
            skipped += 1
            continue
        logger.info("%s sox_ret 정정: %+.2f → %+.2f (교차검증 %s)", d, float(got), base,
                    ", ".join(f"{s}{v:+.2f}" for s, v in cross.items() if v is not None))
        fixed += 1
        if apply:
            with get_db() as (conn, cursor):
                cursor.execute(
                    "UPDATE market_snapshot SET sox_ret = %s, source = 'repaired' "
                    "WHERE snapshot_date = %s AND slot = %s",
                    (base, d, SLOT_OBS),
                )
                conn.commit()
    logger.info("sox_ret 정정 %s — 대상 %d건 · 교차검증 미통과 %d건",
                "완료" if apply else "예정(dry-run)", fixed, skipped)


def main() -> int:
    ap = argparse.ArgumentParser(description="market_snapshot 관측 슬롯 소급 백필")
    ap.add_argument("--verify", action="store_true", help="겹치는 구간 대조만(쓰기 없음)")
    ap.add_argument("--dry-run", action="store_true", help="채울 행 미리보기")
    ap.add_argument("--apply", action="store_true", help="실제 적재")
    ap.add_argument("--repair-sox", action="store_true", help="결함 sox_ret 정정")
    args = ap.parse_args()

    dates = _report_dates()
    if not dates:
        logger.error("리포트 날짜가 없다 — 백필 대상 구간을 정할 수 없음")
        return 1
    rows = _existing()
    logger.info("대상 구간 %s ~ %s (%d일) · 관측 슬롯 기존 행 %d",
                dates[0], dates[-1], len(dates), len(rows))

    if args.repair_sox:
        repair_sox(rows, apply=args.apply)
        return 0

    verdict = verify(dates, rows)
    cols = [c for c, ok in verdict.items() if ok]
    if args.verify:
        return 0
    if not cols:
        logger.error("검증을 통과한 컬럼이 없다 — 적재하지 않는다")
        return 1
    backfill(dates, rows, cols, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
