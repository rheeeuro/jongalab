"""주도 섹터(테마) 일간 리포트 데이터 접근"""
import json
from datetime import date, datetime

from core.db import get_db


def save_sector_reports(sectors: list[dict]):
    """테마그룹 분석 결과를 일괄 저장 (UPSERT)

    sectors 각 항목 예시:
        {
            "thema_grp_cd": "319",
            "thema_nm": "반도체",
            "stk_num": 5,
            "flu_rt": 0.02,
            "dt_prft_rt": 157.80,
            "main_stk": "삼성전자",
            "rising_stk_num": 3,
            "fall_stk_num": 1,
            "rank_no": 1,
            "stocks": [
                {"stk_cd": "005930", "stk_nm": "삼성전자", "cur_prc": "57800", "flu_rt": "1.20"},
                ...
            ]
        }
    """
    if not sectors:
        return

    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM daily_sector_report WHERE report_date = CURDATE()")

        query = """
            INSERT INTO daily_sector_report
            (report_date, thema_grp_cd, thema_nm, stk_num, flu_rt, dt_prft_rt,
             main_stk, rising_stk_num, fall_stk_num, rank_no, stocks)
            VALUES (CURDATE(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        for s in sectors:
            stocks_json = json.dumps(s.get("stocks", []), ensure_ascii=False)
            cursor.execute(query, (
                s["thema_grp_cd"], s["thema_nm"],
                s.get("stk_num", 0), s.get("flu_rt", 0.0),
                s.get("dt_prft_rt", 0.0), s.get("main_stk", ""),
                s.get("rising_stk_num", 0), s.get("fall_stk_num", 0),
                s.get("rank_no", 0), stocks_json,
            ))
        conn.commit()


def get_sector_reports_by_date(report_date: str) -> list[dict]:
    """특정 날짜의 주도 섹터 목록 (순위순)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM daily_sector_report
               WHERE report_date = %s
               ORDER BY rank_no ASC""",
            (report_date,),
        )
        results = cursor.fetchall()
        for row in results:
            _serialize(row)
        return results


def get_top_themes_by_dates(dates: list[str], limit: int = 3) -> dict[str, list[str]]:
    """여러 날짜의 상위 주도 테마명을 한 번에 조회.

    반환: {date: [thema_nm, ...]}  (날짜별 rank_no 순 최대 limit개)
    """
    if not dates:
        return {}

    placeholders = ",".join(["%s"] * len(dates))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT report_date, thema_nm, rank_no
                  FROM daily_sector_report
                 WHERE report_date IN ({placeholders})
                 ORDER BY report_date DESC, rank_no ASC""",
            tuple(dates),
        )
        rows = cursor.fetchall()

    result: dict[str, list[str]] = {}
    for row in rows:
        d = row["report_date"]
        key = d.isoformat().split("T")[0] if isinstance(d, (date, datetime)) else str(d)
        themes = result.setdefault(key, [])
        if len(themes) < limit:
            themes.append(row["thema_nm"])
    return result


def get_sector_report_dates(limit: int = 30) -> list[str]:
    """섹터 리포트가 존재하는 날짜 목록"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT DISTINCT report_date
               FROM daily_sector_report
               ORDER BY report_date DESC
               LIMIT %s""",
            (limit,),
        )
        results = cursor.fetchall()
        return [
            row["report_date"].isoformat()
            if isinstance(row["report_date"], (date, datetime))
            else str(row["report_date"])
            for row in results
        ]


def _serialize(row: dict):
    """날짜 및 JSON 필드 직렬화"""
    if isinstance(row.get("report_date"), (date, datetime)):
        row["report_date"] = row["report_date"].isoformat().split("T")[0]
    if isinstance(row.get("created_at"), datetime):
        row["created_at"] = row["created_at"].isoformat()
    # stocks JSON 문자열 → list 변환
    if isinstance(row.get("stocks"), str):
        try:
            row["stocks"] = json.loads(row["stocks"])
        except (json.JSONDecodeError, TypeError):
            row["stocks"] = []
