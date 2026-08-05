"""Edge Ledger 데이터 접근 (edge_rule · edge_rule_daily).

가설(rule)은 candidate 로 태어나 rule_evaluator 가 매일 채점하고, 표본·성적이 차면
관리자 API 로만 live 승격된다(자동 승격 없음). raw SQL 은 여기서만.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from core.db import get_db

# exit_label 로 허용되는 결과 라벨 컬럼(daily_stock_report). 오타/오설정으로 영원히
# 준비 안 되는(readiness=False) rule 을 만드는 걸 막는다. 라벨 추가 시 여기 등록.
ALLOWED_EXIT_LABELS = (
    "next_open_ret", "next_high_ret", "next_low_ret", "next_close_ret",
    "nxt_open_ret", "gap_nxt_pct", "gap_krx_pct", "exec_leg_ret",
)


def _serialize(row: dict) -> dict:
    """JSON 컬럼 파싱 + 날짜/Decimal 직렬화."""
    for k in ("predicate", "stats", "decision", "matched"):
        v = row.get(k)
        if isinstance(v, str):
            try:
                row[k] = json.loads(v)
            except (ValueError, TypeError):
                row[k] = None
    for k, v in list(row.items()):
        if isinstance(v, (date, datetime)):
            row[k] = v.isoformat()
        elif isinstance(v, Decimal):
            row[k] = float(v)
    return row


# ── edge_rule CRUD ──

def create_rule(
    name: str,
    family: str,
    description: str,
    predicate: list,
    exit_label: str = "exec_leg_ret",
    min_sample: int = 40,
    registered_at: str | None = None,
    status: str = "candidate",
    title: str | None = None,
    role: str = "selector",
) -> int:
    """신규 rule 등록. registered_at 미지정 시 오늘(사전 등록일). 반환: rule id.
    title 은 카드 제목(한글) — NULL 이면 프론트가 name 슬러그로 폴백.
    role 은 selector/veto/benchmark (검증은 라우터가 edge_policy.ROLES 로 수행)."""
    pred = json.dumps(predicate, ensure_ascii=False)
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO edge_rule
               (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, CURDATE()))""",
            (name, title, family, role, description, pred, exit_label, status, int(min_sample), registered_at),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_rules(status: str | None = None, exclude_retired: bool = False) -> list[dict]:
    """rule 목록. status 지정 시 그 상태만, exclude_retired 면 retired 제외.

    ⚠️ evaluator·백필은 **retired 를 포함**한다(2026-07-31) — retire 는 '판정 종결(알림·게이트
    대상 아님)'이고 채점은 계속한다. 실매매 개입은 `status='live'` 조회만 하므로 안전하다.
    """
    cond, params = "", []
    if status:
        cond, params = " WHERE status = %s", [status]
    elif exclude_retired:
        cond = " WHERE status <> 'retired'"
    with get_db() as (conn, cursor):
        cursor.execute(
            f"SELECT * FROM edge_rule{cond} ORDER BY family, name", tuple(params)
        )
        return [_serialize(r) for r in cursor.fetchall()]


def get_rule(rule_id: int) -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM edge_rule WHERE id = %s", (rule_id,))
        row = cursor.fetchone()
        return _serialize(row) if row else None


def get_rule_by_name(name: str) -> dict | None:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM edge_rule WHERE name = %s", (name,))
        row = cursor.fetchone()
        return _serialize(row) if row else None


def update_rule_stats(rule_id: int, stats: dict) -> None:
    """evaluator 가 재계산한 누적 통계 캐시 갱신."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE edge_rule SET stats = %s WHERE id = %s",
            (json.dumps(stats, ensure_ascii=False, default=str), rule_id),
        )
        conn.commit()


def update_rule_decision(rule_id: int, decision: dict) -> None:
    """판정 기록 갱신(sql/39). stats 와 달리 **재계산 대상이 아닌 영구 기록**이다 —
    한 번 판정한 rule 을 다시 시험하지 않기 위한 근거이므로 덮어쓸 때 주의한다."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "UPDATE edge_rule SET decision = %s WHERE id = %s",
            (json.dumps(decision, ensure_ascii=False, default=str), rule_id),
        )
        conn.commit()


def delete_rule(rule_id: int) -> int:
    """rule 행 삭제 — **당일 오등록 철회 전용**. 반환: 삭제된 행 수.

    원장은 사전등록이 규율이라 rule 은 원칙적으로 불변이고, 종료는 `status='retired'` 다
    (retire 후에도 채점은 계속해 "그때 폐기가 옳았나"를 사후 확인한다 — 2026-07-31 결정).
    그래서 이 함수는 **채점 이력이 없는**(edge_rule_daily 0행) 같은 날 오등록만 지운다 —
    표본이 쌓인 rule 을 지우면 그 가설을 시험했다는 사실 자체가 사라져 다중검정 보정이 무의미해진다.
    이력이 있으면 ValueError 를 던져 retire 로 유도한다.
    """
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) AS n FROM edge_rule_daily WHERE rule_id = %s", (rule_id,))
        scored = int((cursor.fetchone() or {}).get("n") or 0)
        if scored:
            raise ValueError(
                f"rule {rule_id} 은 채점 이력 {scored}행이 있어 삭제할 수 없습니다 — "
                "종료는 status='retired' 로 하세요(채점은 계속되며 사후 검증이 가능합니다)"
            )
        cursor.execute("DELETE FROM edge_rule WHERE id = %s", (rule_id,))
        conn.commit()
        return cursor.rowcount


def set_rule_status(rule_id: int, status: str) -> None:
    """상태 전이 — live 면 promoted_at, retired 면 retired_at 타임스탬프도 찍는다."""
    ts = ""
    if status == "live":
        ts = ", promoted_at = CURRENT_TIMESTAMP"
    elif status == "retired":
        ts = ", retired_at = CURRENT_TIMESTAMP"
    with get_db() as (conn, cursor):
        cursor.execute(
            f"UPDATE edge_rule SET status = %s{ts} WHERE id = %s", (status, rule_id)
        )
        conn.commit()


# (2026-08-05) `count_promoted_in_month` 는 월 승격 상한 폐지와 함께 삭제했다.
# 승격 이력이 필요하면 `edge_rule.promoted_at` 을 직접 조회한다.


# ── edge_rule_daily ──

def upsert_rule_daily(
    rule_id: int, report_date: str, n_matched: int,
    mean_net_ret: float | None, matched: list,
) -> None:
    """rule×날짜 평가 결과 upsert(재실행 멱등)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """INSERT INTO edge_rule_daily (rule_id, report_date, n_matched, mean_net_ret, matched)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 n_matched = VALUES(n_matched),
                 mean_net_ret = VALUES(mean_net_ret),
                 matched = VALUES(matched)""",
            (rule_id, report_date, int(n_matched), mean_net_ret,
             json.dumps(matched, ensure_ascii=False, default=str)),
        )
        conn.commit()


def get_scored_dates(rule_id: int) -> set[str]:
    """이미 채점된 report_date 집합 (catch-up 에서 제외용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT report_date FROM edge_rule_daily WHERE rule_id = %s", (rule_id,)
        )
        return {
            r["report_date"].isoformat() if isinstance(r["report_date"], (date, datetime))
            else str(r["report_date"])
            for r in cursor.fetchall()
        }


def get_rule_daily(rule_id: int, days: int = 60) -> list[dict]:
    """일별 성적 시계열(최신 days 일, 오래된→최신). 스코어보드 차트용.

    matched(일별 매칭 종목 전체 JSON)는 제외한다 — 광역 rule 은 하루 수십 종목이라
    60일치를 다 실으면 페이로드가 수백 KB 로 자란다. 최신 매칭은 get_latest_matched 로.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT id, rule_id, report_date, n_matched, mean_net_ret, created_at FROM (
                   SELECT id, rule_id, report_date, n_matched, mean_net_ret, created_at
                     FROM edge_rule_daily WHERE rule_id = %s
                    ORDER BY report_date DESC LIMIT %s
               ) t ORDER BY report_date ASC""",
            (rule_id, int(days)),
        )
        return [_serialize(r) for r in cursor.fetchall()]


def get_latest_matched(rule_id: int) -> dict | None:
    """매칭이 있었던 가장 최신 날짜의 {report_date, matched} — 상세 뷰 '최근 매칭 종목'용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT report_date, matched FROM edge_rule_daily
                WHERE rule_id = %s AND n_matched > 0
                ORDER BY report_date DESC LIMIT 1""",
            (rule_id,),
        )
        row = cursor.fetchone()
        return _serialize(row) if row else None


def get_rule_matched_history(rule_id: int, days: int = 30) -> list[dict]:
    """매칭이 있었던 최근 days 일의 {report_date, n_matched, mean_net_ret, matched} (최신→과거).

    상세 페이지 '날짜별 매칭 기록'용 — daily 시계열에서 페이로드 때문에 뺀 matched 를
    날짜 역순으로 제한해 내려준다. 저장 JSON(code/name/ret/low)에 당일 리포트의
    등락률(change_pct)·현행 점수 선정 여부(selected)를 조인해 복기 맥락을 붙인다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT report_date, n_matched, mean_net_ret, matched
                 FROM edge_rule_daily
                WHERE rule_id = %s AND n_matched > 0
                ORDER BY report_date DESC LIMIT %s""",
            (rule_id, int(days)),
        )
        rows = [_serialize(r) for r in cursor.fetchall()]
        if not rows:
            return rows
        placeholders = ", ".join(["%s"] * len(rows))
        cursor.execute(
            f"""SELECT report_date, stock_code, change_pct, selected
                  FROM daily_stock_report
                 WHERE report_date IN ({placeholders})""",
            tuple(r["report_date"] for r in rows),
        )
        report_by_date_code = {}
        for r in cursor.fetchall():
            d = r["report_date"].isoformat() if isinstance(r["report_date"], (date, datetime)) else str(r["report_date"])
            report_by_date_code[(d, r["stock_code"])] = r
        for row in rows:
            for m in row.get("matched") or []:
                extra = report_by_date_code.get((row["report_date"], m.get("code")))
                m["change_pct"] = (
                    round(float(extra["change_pct"]), 2)
                    if extra and extra.get("change_pct") is not None else None
                )
                m["selected"] = int(extra["selected"]) if extra and extra.get("selected") is not None else None
        return rows


def get_rule_daily_since(rule_id: int, since: str) -> list[dict]:
    """registered_at(=since) 이후 채점 결과 전체(오래된→최신) — 누적 통계 재계산용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM edge_rule_daily
               WHERE rule_id = %s AND report_date >= %s
               ORDER BY report_date ASC""",
            (rule_id, since),
        )
        return [_serialize(r) for r in cursor.fetchall()]


def get_universe_label_totals(label: str) -> dict[str, tuple[float, int]]:
    """날짜별 유니버스 전체의 (라벨 합계, 종목 수) — 초과수익 채점의 기준선.

    rule_evaluator 가 '유니버스 자기제외 평균'(그날 유니버스에서 **그 rule 이 매칭한
    종목을 뺀** 나머지의 평균)을 만들 때 쓴다. 합계·개수로 돌려주는 이유는 rule 마다
    빼야 할 종목이 달라, 여기서 평균을 내면 leave-one-out 을 못 하기 때문이다.

    label 은 ALLOWED_EXIT_LABELS 로 화이트리스트 검증한다(컬럼명이라 바인딩 불가).
    """
    if label not in ALLOWED_EXIT_LABELS:
        raise ValueError(f"허용되지 않은 exit_label: {label}")
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT report_date, SUM({label}) AS s, COUNT({label}) AS c
                FROM daily_stock_report
                WHERE {label} IS NOT NULL
                GROUP BY report_date"""
        )
        out: dict[str, tuple[float, int]] = {}
        for r in cursor.fetchall():
            d = r["report_date"]
            key = d.isoformat() if isinstance(d, (date, datetime)) else str(d)
            out[key] = (float(r["s"]), int(r["c"]))
        return out
