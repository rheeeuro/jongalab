"""Edge Ledger **읽기 전용** 접근 (jongalab DB) — 집행 레이어 rule 평가용.

trading 은 원장을 **절대 쓰지 않는다**(등록·승격·강등·채점은 전부 jongalab 소관).
여기 있는 건 "지금 live 인 집행 레이어 rule 이 무엇인가"와 "그 rule 을 평가할 종목 행"뿐이다.
regime_gate·macro_gate·news_veto 가 jongalab DB 를 읽는 것과 같은 패턴(`get_jongalab_db`).

왜 필요한가: NXT 야간 갭(`nxt_gap_pct`)은 19:50 주문 직전에만 알 수 있어 선정 레이어가 쓸 수
없다. 그 값을 쓰는 rule 을 원장 밖 하드코딩으로 집행하면 채점·강등 감시가 사라지므로
(2026-08-03 실제로 그렇게 했다가 되돌림), 집행기가 원장을 읽어 predicate 를 평가한다.
"""
import json

from core.db import get_jongalab_db


def _rows(cursor) -> list[dict]:
    out = []
    for r in cursor.fetchall():
        row = dict(r)
        for k in ("predicate", "stats"):
            v = row.get(k)
            if isinstance(v, str):
                try:
                    row[k] = json.loads(v)
                except (ValueError, TypeError):
                    row[k] = None
        out.append(row)
    return out


def get_live_rules() -> list[dict]:
    """live rule 전체(id·name·role·predicate·exit_label). 조회 실패는 호출부가 처리."""
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT id, name, title, family, role, predicate, exit_label "
            "FROM edge_rule WHERE status = 'live' ORDER BY id"
        )
        return _rows(cursor)


def get_selected_count(report_date: str) -> int | None:
    """그날 선정 종목 수 — '점수 top-N 에도 들었는가' 판정의 N 근사값. 없으면 None.

    jongalab `TRADED_TOP_N` 은 closing_bet 모듈 상수라 trading 이 직접 읽을 수 없다. hybrid
    선정은 (rule 매칭 우선 + 잔여 슬롯 점수순)으로 **총 상한이 top_n** 이므로 선정 종목 수가
    곧 그 값이다(풀이 상한보다 작은 날만 작아지고, 그때는 판정이 더 보수적으로 기울 뿐이다).
    """
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT COUNT(*) AS n FROM daily_stock_report "
            "WHERE report_date = %s AND selected = 1",
            (report_date,),
        )
        n = int((cursor.fetchone() or {}).get("n") or 0)
        return n or None


def get_report_rows(report_date: str, stock_codes: list[str]) -> dict[str, dict]:
    """해당 거래일 `daily_stock_report` 행을 종목코드 → 행 dict 로. 없는 종목은 키 없음.

    report_date: 'YYYY-MM-DD'. stock_codes: 6자리 코드(접미사 없음 — 저장 형식과 동일).
    predicate 가 참조할 수 있는 컬럼을 그대로 넘긴다(`SELECT *`) — 컬럼 화이트리스트를 여기
    또 두면 jongalab `edge_policy.EXECUTION_TIME_COLS` 와 두 곳이 어긋난다.
    """
    if not stock_codes:
        return {}
    ph = ",".join(["%s"] * len(stock_codes))
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            f"SELECT * FROM daily_stock_report WHERE report_date = %s AND stock_code IN ({ph})",
            (report_date, *stock_codes),
        )
        return {r["stock_code"]: dict(r) for r in cursor.fetchall()}
