"""불변 감사로그 — 모든 주문 의도 + 키움 응답 원문을 append-only 로 적재.

자동매매의 사후 추적·정산 근거. UPDATE/DELETE 하지 않는다.
"""
import json
from typing import Optional

from core.db import get_db


def append(event: str, stk_cd: Optional[str], payload: dict) -> None:
    """감사 이벤트 1건 기록 (payload 는 JSON 직렬화)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO audit_log (event, stk_cd, payload) VALUES (%s, %s, %s)",
            (event, stk_cd, json.dumps(payload, ensure_ascii=False, default=str)),
        )
        conn.commit()


def mark_worker_done(worker: str) -> None:
    """워커가 '오늘 정상 완료'했음을 남기는 완료 마커 (watchdog/dead-man's switch 용).

    무거래(no-op) 완료도 포함해, 마커가 없으면 곧 '해당 워커가 안 돌았다'로 단정할 수 있게 한다.
    이 호출이 워커 본연의 결과를 가리지 않도록 예외는 삼킨다(이미 일은 끝난 시점).
    """
    try:
        append("worker_done", worker, {})
    except Exception:  # noqa: BLE001 — 마커 실패가 워커 성공/실패를 바꾸면 안 된다
        import logging
        logging.getLogger("audit_log").warning("worker_done 마커 기록 실패: %s", worker)


def workers_done_today(date_dash: str) -> set[str]:
    """오늘(YYYY-MM-DD) 완료 마커를 남긴 워커 이름 집합 — watchdog 가 누락을 판정한다."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT DISTINCT stk_cd FROM audit_log "
            "WHERE event = 'worker_done' "
            "AND created_at >= %s AND created_at < %s + INTERVAL 1 DAY",
            (date_dash, date_dash),
        )
        return {r["stk_cd"] for r in cursor.fetchall() if r.get("stk_cd")}


def realized_by_date(date_dash: str) -> dict:
    """해당 날짜(YYYY-MM-DD) 종목별 실현손익 합 — 일별 상세용 (paper 청산 기준)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT stk_cd, payload FROM audit_log "
            "WHERE event IN ('sell_filled_paper', 'sell_filled_live') "
            "AND created_at >= %s AND created_at < %s + INTERVAL 1 DAY",
            (date_dash, date_dash),
        )
        rows = cursor.fetchall()
    agg: dict[str, int] = {}
    for r in rows:
        payload = r.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = {}
        realized = (payload or {}).get("realized") or 0
        agg[r["stk_cd"]] = agg.get(r["stk_cd"], 0) + realized
    return agg


def last_heartbeat():
    """가장 최근 하트비트 1건 (monitor_poll/buy_poll) — 없으면 None.

    어느 폴링 워커든 살아 있으면 대시보드가 '가동 중'으로 본다. event(매도 모니터 vs 매수)와
    payload(buy_poll 의 venue: krx/nxt)로 실제 돌고 있는 워커를 식별할 수 있다."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT event, stk_cd, payload, created_at FROM audit_log "
            "WHERE event IN ('monitor_poll', 'buy_poll') ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    if row and isinstance(row.get("payload"), str):
        try:
            row["payload"] = json.loads(row["payload"])
        except (ValueError, TypeError):
            pass
    return row


# 폴링 워커가 남기는 활동 이벤트 (하트비트 monitor_poll/buy_poll 은 제외 — 로그 피드 노이즈 방지).
#   매도 모니터: monitor_*  /  매수 집행: buy_start, buy_exec(눌림/데드라인), buy_skip
_ACTIVITY_EVENTS = (
    "monitor_start", "monitor_trail", "monitor_stop", "monitor_hardstop",
    "buy_start", "buy_exec", "buy_skip",
)


def list_activity_events(limit: int = 50, date_dash: str | None = None) -> list[dict]:
    """폴링 활동 로그 — 매도(스탑 상향/발동) + 매수(집행/스킵/시작) (최신순). payload 는 dict 로 파싱.
    date_dash(YYYY-MM-DD) 를 주면 그 날짜 이벤트만 (모니터 탭: 오늘만)."""
    placeholders = ", ".join(["%s"] * len(_ACTIVITY_EVENTS))
    where = f"event IN ({placeholders})"
    params: list = [*_ACTIVITY_EVENTS]
    if date_dash:
        where += " AND created_at >= %s AND created_at < %s + INTERVAL 1 DAY"
        params += [date_dash, date_dash]
    params.append(int(limit))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT id, event, stk_cd, payload, created_at FROM audit_log "
            f"WHERE {where} ORDER BY id DESC LIMIT %s",
            tuple(params),
        )
        rows = cursor.fetchall()
    for r in rows:
        if isinstance(r.get("payload"), str):
            try:
                r["payload"] = json.loads(r["payload"])
            except (ValueError, TypeError):
                pass
    return rows


def list_recent(limit: int = 50) -> list[dict]:
    """최근 감사 이벤트 (대시보드용, 최신순). payload 는 dict 로 파싱."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, event, stk_cd, payload, created_at "
            "FROM audit_log ORDER BY id DESC LIMIT %s",
            (int(limit),),
        )
        rows = cursor.fetchall()
    for r in rows:
        if isinstance(r.get("payload"), str):
            try:
                r["payload"] = json.loads(r["payload"])
            except (ValueError, TypeError):
                pass
    return rows
