"""불변 감사로그 — 모든 주문 의도 + 키움 응답 원문을 append-only 로 적재.

자동매매의 사후 추적·정산 근거. UPDATE/DELETE 하지 않는다.
"""
import re
import json
from typing import Optional

from core.db import get_db

# 키움 거부 메시지에서 사람이 읽을 부분만 추출 — "[2000](855056:매수증거금이 부족합니다...)" → 안쪽 메시지.
_KIWOOM_MSG_RE = re.compile(r"\(\d+:(.+)\)\s*$")


def _clean_kiwoom_msg(msg: str) -> str:
    m = _KIWOOM_MSG_RE.search(msg or "")
    return (m.group(1) if m else (msg or "")).strip()


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


def has_sell_between(stk_cd: str, start_dt: str, end_dt: str) -> bool:
    """[start_dt, end_dt) 사이에 이 종목 매도 체결이 있었는지(datetime 문자열, 포함~미포함).

    분할/이월 청산 판정용 — 같은 매수(1회)를 여러 날에 나눠 팔면, 뒤 매도일은 '이미 한 번 판
    뒤의 연속 청산'이다. 이때 모달이 원매수일까지 거슬러 올라가지 않도록(=매도 당일만 보도록)
    호출부가 이 신호로 구간 시작을 조정한다. 하한을 매수일 오후(15:00)로 주면, 매수 전 그날
    오전에 끝난 '다른 사이클'의 청산은 세지 않는다."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT 1 FROM audit_log WHERE stk_cd = %s "
            "AND event IN ('sell_filled_paper', 'sell_filled_live') "
            "AND created_at >= %s AND created_at < %s LIMIT 1",
            (stk_cd, start_dt, end_dt),
        )
        return cursor.fetchone() is not None


def latest_manual_buys_before(date_dash: str) -> dict:
    """각 종목의 'date_dash(YYYY-MM-DD) 0시 이전' 가장 최근 수동 매수(manual_buy_link) 1건.

    NXT 일일 한도 초과로 자동 매수가 막힌 분을 사람이 수동 체결해 연동한 기록 — order 테이블엔 없고
    audit_log 로만 남아 라운드트립 매수처 짝짓기에서 누락된다. order 매수와 함께 후보로 쓰도록 order 와
    같은 모양으로 돌려준다. created_at(매수 시각)은 이 수동 매수가 메우는 직전 자동매수 시도
    (buy_exec/buy_blocked/buy_intended)의 시각을 쓴다 — 그게 실제 NXT 체결 시점이다(연동은 보통
    새벽 일괄이라 링크 시각은 날짜가 밀려 있음). 매칭이 없으면 링크 시각.
    반환: {stk_cd: {stk_cd, qty, price, fill_price, filled_qty, created_at}} (order 매수와 동일 형태)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT a.stk_cd, a.payload, a.created_at FROM audit_log a "
            "JOIN (SELECT stk_cd, MAX(id) AS mid FROM audit_log "
            "      WHERE event = 'manual_buy_link' AND created_at < %s GROUP BY stk_cd) m "
            "  ON a.id = m.mid",
            (date_dash,),
        )
        links = cursor.fetchall()
        out: dict[str, dict] = {}
        for r in links:
            payload = r["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (ValueError, TypeError):
                    payload = {}
            payload = payload or {}
            price = abs(int(payload.get("avg_price") or 0))
            qty = int(payload.get("qty") or 0)
            cursor.execute(
                "SELECT created_at FROM audit_log WHERE stk_cd = %s "
                "AND event IN ('buy_exec', 'buy_blocked', 'buy_intended') "
                "AND created_at <= %s ORDER BY id DESC LIMIT 1",
                (r["stk_cd"], r["created_at"]),
            )
            hit = cursor.fetchone()
            out[r["stk_cd"]] = {
                "stk_cd": r["stk_cd"], "qty": qty, "price": price,
                "fill_price": price, "filled_qty": qty,
                "created_at": hit["created_at"] if hit else r["created_at"],
            }
        return out


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
    "regime_gate", "futures_gate",  # 시드 축소 사유(레짐 역전 / 선물 하락 섹터 감액)
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


# 한 종목 트레일에서 제외할 노이즈 — 하트비트·완료마커·주문응답 원문(키움 resp 그대로라 길다).
_TRAIL_EXCLUDE = ("monitor_poll", "buy_poll", "worker_done", "buy_response", "sell_response")


def list_by_stock(stk_cd: str, start_dt: str, end_dt: str, limit: int = 200) -> list[dict]:
    """한 종목의 매매 트레일 — [start_dt, end_dt] 시각 구간('YYYY-MM-DD HH:MM:SS', 포함) 감사
    이벤트(시간 오름차순).

    대시보드에서 청산 종목을 누르면 '그 종목에 워커가 무슨 일을 했는지'(매수 집행 → 갭/스탑
    모니터 → 매도 체결)를 시간순으로 보여주기 위한 조회. 구간은 한 매매 사이클(매수날 12시~매도날
    12시)로 좁혀, 같은 종목을 여러 날 매매해도 인접 사이클 이벤트가 섞이지 않는다. payload 는 dict 로 파싱."""
    placeholders = ", ".join(["%s"] * len(_TRAIL_EXCLUDE))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT id, event, stk_cd, payload, created_at FROM audit_log "
            f"WHERE stk_cd = %s AND event NOT IN ({placeholders}) "
            f"AND created_at >= %s AND created_at <= %s "
            f"ORDER BY id ASC LIMIT %s",
            (stk_cd, *_TRAIL_EXCLUDE, start_dt, end_dt, int(limit)),
        )
        rows = cursor.fetchall()
    for r in rows:
        if isinstance(r.get("payload"), str):
            try:
                r["payload"] = json.loads(r["payload"])
            except (ValueError, TypeError):
                pass
    return rows


def reject_reasons_by_order_ids(order_ids: list[int]) -> dict[int, str]:
    """거부된 주문의 키움 거부 사유 맵 {order_id: 메시지}.

    execute_buy/execute_sell 가 거부 시 남기는 buy_rejected/sell_rejected payload
    (order_id + resp.return_msg)에서 뽑아, 대시보드가 '왜 체결 안 됐나'를 보여주게 한다.
    payload 는 JSON 컬럼 — order_id 로 DB 필터 후 메시지는 Python 에서 파싱(중첩 resp 안전)."""
    ids = {int(i) for i in order_ids if i is not None}
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT payload FROM audit_log "
            f"WHERE event IN ('buy_rejected', 'sell_rejected') "
            f"AND JSON_VALUE(payload, '$.order_id') IN ({placeholders})",
            tuple(str(i) for i in ids),
        )
        rows = cursor.fetchall()
    out: dict[int, str] = {}
    for r in rows:
        payload = r.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                continue
        payload = payload or {}
        oid = payload.get("order_id")
        msg = (payload.get("resp") or {}).get("return_msg") or ""
        msg = _clean_kiwoom_msg(msg)
        if oid is not None and msg:
            out[int(oid)] = msg
    return out


# 주문 행이 안 생기는 '매수 안 함' 이벤트 — 전송 전 스킵/차단(거래내역 탭이 사유와 함께 보여준다).
#   buy_skip: 블록리스트 제외·배분 0주(워커) / buy_blocked: 리스크 차단 / buy_skipped: 주문가능액 부족·수량 0(집행기)
_SKIP_EVENTS = ("buy_skip", "buy_blocked", "buy_skipped")


def buy_skips_by_month(month: str) -> list[dict]:
    """해당 월(YYYYMM) 매수 스킵/차단 — order 행이 없는 미체결을 order 와 같은 모양으로 돌려준다.

    거래내역 탭이 주문과 한 목록에 섞어 '왜 안 샀나'를 보여주게 한다(status='skipped', reason 동봉).
    같은 날·같은 종목은 최신 1건만(여러 윈도우 중복 방지)."""
    first_day = f"{month[:4]}-{month[4:6]}-01"
    placeholders = ", ".join(["%s"] * len(_SKIP_EVENTS))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT id, event, stk_cd, payload, created_at FROM audit_log "
            f"WHERE event IN ({placeholders}) AND stk_cd IS NOT NULL "
            f"AND created_at >= %s AND created_at < %s + INTERVAL 1 MONTH "
            f"ORDER BY id DESC",
            (*_SKIP_EVENTS, first_day, first_day),
        )
        rows = cursor.fetchall()
    out: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        payload = r.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = {}
        payload = payload or {}
        dedup = (str(r["created_at"])[:10], r["stk_cd"])  # (날짜, 종목) — id DESC 라 먼저 본 게 최신
        if dedup in seen:
            continue
        seen.add(dedup)
        reason = payload.get("reason") or "스킵"
        if reason == "blocklist":
            reason = "블록리스트 제외"
        out.append({
            "id": r["id"], "stk_cd": r["stk_cd"], "side": "buy",
            "qty": 0, "price": 0, "fill_price": None, "filled_qty": 0,
            "kiwoom_ord_no": None, "status": "skipped", "reason": reason,
            "created_at": r["created_at"], "kind": "skip",
        })
    return out


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
