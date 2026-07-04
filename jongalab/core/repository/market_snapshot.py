"""시장 스냅샷 데이터 접근 (일 단위, snapshot_date PK).

gap_check --base-nxt(19:50)가 save_market_snapshot 로 1행 upsert 하고, 엣지 연구
(F2 해외 동조·레짐)에서 get_market_snapshots 로 report_date 와 조인한다.
"""
from datetime import date, datetime

from core.db import get_db

_FIELDS = (
    "kospi_ret", "kosdaq_ret", "nq_fut_ret", "spx_ret", "sox_ret",
    "vix", "usdkrw_ret", "k200f_day_ret", "k200f_night_ret",
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
