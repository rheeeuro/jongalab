"""시장 스냅샷 데이터 접근 (일 단위, snapshot_date PK).

gap_check --base-nxt(19:50)가 save_market_snapshot 로 1행 upsert 하고, 엣지 연구
(F2 해외 동조·레짐)에서 get_market_snapshots 로 report_date 와 조인한다.
"""
from datetime import date, datetime

from core.db import get_db

_FIELDS = (
    "kospi_ret", "kosdaq_ret", "nq_fut_ret", "spx_ret", "sox_ret",
    "vix", "usdkrw_ret", "wti_ret", "ewy_ret", "koru_ret", "skhy_ret",
    "k200f_day_ret", "k200f_night_ret",
    # 뉴스 기반 시황 톤(연구용) — 값의 시점 의미는 sql/60 주석 참고.
    "news_macro_tone", "news_macro_cnt", "news_sector_tone", "news_sector_cnt",
)


def save_market_snapshot(row: dict) -> None:
    """snapshot_date 기준 upsert. row: {snapshot_date, <_FIELDS...>}. 누락 필드는 NULL."""
    snapshot_date = row.get("snapshot_date")
    if not snapshot_date:
        return
    vals = [row.get(f) for f in _FIELDS]
    cols = ", ".join(_FIELDS)
    placeholders = ", ".join(["%s"] * len(_FIELDS))
    updates = ", ".join(f"{f} = VALUES({f})" for f in _FIELDS)
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""INSERT INTO market_snapshot (snapshot_date, {cols})
                VALUES (%s, {placeholders})
                ON DUPLICATE KEY UPDATE {updates}""",
            (snapshot_date, *vals),
        )
        conn.commit()


def save_after_hours_breadth(snapshot_date: str, up3_cnt: int | None, dn3_cnt: int | None) -> None:
    """시간외단일가 ±3% 이상 종목 수 upsert (after_hours_labels 워커, 18:05).

    ah_* 두 컬럼만 갱신한다 — save_market_snapshot(_FIELDS 전체 upsert)를 쓰면
    19:50 gap_check 가 채운 지수 필드를 NULL 로 덮으므로 전용 함수로 분리.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO market_snapshot (snapshot_date, ah_up3_cnt, ah_dn3_cnt)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   ah_up3_cnt = COALESCE(VALUES(ah_up3_cnt), ah_up3_cnt),
                   ah_dn3_cnt = COALESCE(VALUES(ah_dn3_cnt), ah_dn3_cnt)""",
            (snapshot_date, up3_cnt, dn3_cnt),
        )
        conn.commit()


def get_market_snapshots(dates: list[str]) -> dict[str, dict]:
    """여러 날짜의 시장 스냅샷을 {date: row} 로 조회. 없는 날짜는 키 없음."""
    if not dates:
        return {}
    placeholders = ",".join(["%s"] * len(dates))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT * FROM market_snapshot WHERE snapshot_date IN ({placeholders})",
            tuple(dates),
        )
        rows = cursor.fetchall()

    out: dict[str, dict] = {}
    for row in rows:
        d = row.get("snapshot_date")
        key = d.isoformat() if isinstance(d, (date, datetime)) else str(d)
        if isinstance(row.get("captured_at"), datetime):
            row["captured_at"] = row["captured_at"].isoformat()
        row["snapshot_date"] = key
        out[key] = row
    return out
