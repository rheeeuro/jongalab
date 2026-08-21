"""시장 스냅샷 데이터 접근 (날짜 × 시각 슬롯, PK (snapshot_date, slot)).

슬롯 = **그 스냅샷을 굽는 시각**. 레이어마다 자기 집행 직전 슬롯을 쓰고 채점도 같은 슬롯을 읽어
'채점 표본 = 집행 값'을 구조로 보장한다 — 시각에 따라 값이 달라지는 축(선물·VIX·환율·지수)을
쓸 수 있는 것은 이 성질 덕분이다(어느 축이 어느 레이어에 열리는지는 `core/edge_policy` 가 갖는다).

  SLOT_KRX(1430) : gap_check --market-snap 14:30 → KRX 종가매수(15:20) 축. closing_bet 주간 회차.
  SLOT_NXT(1935) : gap_check --market-snap-nxt 19:35 → NXT 매수(19:50) 축. closing_bet 19:40 회차.
                   야간세션이 18:00 에 시작하므로 **야간선물 축은 이 슬롯에만 뜻이 있다**.
  SLOT_OBS(1950) : gap_check --base-nxt 말미(≈19:52) → 확장 관측 + 일봉 소급 백필 적재.
                   주문(19:50)보다 뒤에 굽히므로 **rule 축으로 쓰지 않는다**(사후 정보).

closing_bet 은 실행 시각으로 슬롯을 고르고(`slot_for_now`), rule_evaluator 는 그 rule 이
동작하는 레이어로 고른다 — 두 쪽이 같은 행을 보게 하는 것이 슬롯 분리의 목적이다.
"""
from datetime import date, datetime

from core.db import get_db

SLOT_KRX = "1430"
SLOT_NXT = "1935"
SLOT_OBS = "1950"
SLOTS = (SLOT_KRX, SLOT_NXT, SLOT_OBS)

# NXT 슬롯을 굽는 시각 — closing_bet 의 NXT 회차(19:40)보다 앞이어야 그 회차가 읽을 수 있다.
_NXT_SLOT_FROM = (19, 35)


def slot_for_now(now) -> str:
    """지금 시각에 선정이 읽어야 할 슬롯 — 그 시점에 이미 구워져 있는 가장 최신 축.

    19:35 이후 회차(=NXT 매수 회차)는 야간선물이 살아있는 1935 슬롯을, 그 전 회차는 1430 을 쓴다.
    관측 슬롯(1950)은 주문보다 뒤에 굽히므로 선정이 읽지 않는다.
    """
    return SLOT_NXT if (now.hour, now.minute) >= _NXT_SLOT_FROM else SLOT_KRX

_FIELDS = (
    "kospi_ret", "kosdaq_ret", "nq_fut_ret", "spx_ret", "sox_ret",
    "vix", "usdkrw_ret", "wti_ret", "ewy_ret", "koru_ret", "skhy_ret",
    "k200f_day_ret", "k200f_night_ret",
    # 뉴스 기반 시황 톤(연구용) — 값의 시점 의미는 sql/60 주석 참고.
    "news_macro_tone", "news_macro_cnt", "news_sector_tone", "news_sector_cnt",
)


def save_market_snapshot(row: dict, slot: str = SLOT_OBS, source: str = "live") -> None:
    """(snapshot_date, slot) 기준 upsert. row: {snapshot_date, <_FIELDS...>}. 누락 필드는 NULL.

    같은 슬롯을 다시 구우면 그 슬롯만 덮어쓴다 — 다른 슬롯은 건드리지 않는다(슬롯을 나눈 목적).
    """
    snapshot_date = row.get("snapshot_date")
    if not snapshot_date:
        return
    vals = [row.get(f) for f in _FIELDS]
    cols = ", ".join(_FIELDS)
    placeholders = ", ".join(["%s"] * len(_FIELDS))
    updates = ", ".join(f"{f} = VALUES({f})" for f in _FIELDS)
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""INSERT INTO market_snapshot (snapshot_date, slot, source, {cols})
                VALUES (%s, %s, %s, {placeholders})
                ON DUPLICATE KEY UPDATE source = VALUES(source), {updates}""",
            (snapshot_date, slot, source, *vals),
        )
        conn.commit()


def save_after_hours_breadth(snapshot_date: str, up3_cnt: int | None, dn3_cnt: int | None) -> None:
    """시간외단일가 ±3% 이상 종목 수 upsert (after_hours_labels 워커, 18:05).

    ah_* 두 컬럼만 갱신한다 — save_market_snapshot(_FIELDS 전체 upsert)을 쓰면
    같은 슬롯의 지수 필드를 NULL 로 덮으므로 전용 함수로 분리.
    17:50 수집이라 매수 시점 이후 값이고, 관측 슬롯(1950)에만 적재한다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO market_snapshot (snapshot_date, slot, ah_up3_cnt, ah_dn3_cnt)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   ah_up3_cnt = COALESCE(VALUES(ah_up3_cnt), ah_up3_cnt),
                   ah_dn3_cnt = COALESCE(VALUES(ah_dn3_cnt), ah_dn3_cnt)""",
            (snapshot_date, SLOT_OBS, up3_cnt, dn3_cnt),
        )
        conn.commit()


def get_market_snapshots(dates: list[str], slot: str = SLOT_OBS) -> dict[str, dict]:
    """여러 날짜의 시장 스냅샷을 {date: row} 로 조회 (한 슬롯). 없는 날짜는 키 없음.

    슬롯을 기본값으로 두지 않고 호출부가 명시하는 게 원칙이다 — 채점(rule_evaluator)과
    집행(closing_bet·signal_executor)이 서로 다른 슬롯을 읽으면 게이트가 무의미해진다.
    """
    if not dates:
        return {}
    placeholders = ",".join(["%s"] * len(dates))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT * FROM market_snapshot WHERE slot = %s AND snapshot_date IN ({placeholders})",
            (slot, *dates),
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
