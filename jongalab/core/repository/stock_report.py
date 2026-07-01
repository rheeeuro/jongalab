"""종목일간리포트 데이터 접근"""
import json
from datetime import date, datetime
from decimal import Decimal

from core.db import get_db


def save_stock_reports(candidates: list[dict]):
    """Phase 2 결과를 일괄 저장 (오늘 날짜 기존 데이터 삭제 후 INSERT)"""
    if not candidates:
        return

    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM daily_stock_report WHERE report_date = CURDATE()")

        query = """
            INSERT INTO daily_stock_report
            (report_date, stock_code, stock_name, sector, current_price, change_pct,
             trading_value, market_cap, supply_score,
             inst_net_buy, frgn_net_buy,
             indv_net_buy, prog_net_buy, supply_days, supply_history,
             ma_aligned, near_high, hourly_candles,
             is_leader, is_theme_stock, content_score,
             news_count, news_summary, news_headlines, score, rank_no)
            VALUES (CURDATE(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        for c in candidates:
            supply_history_json = json.dumps(
                c.get("supply_history", []), ensure_ascii=False
            ) if c.get("supply_history") else None
            hourly_candles_json = json.dumps(
                c.get("hourly_candles", []), ensure_ascii=False
            ) if c.get("hourly_candles") else None
            news_headlines_json = json.dumps(
                c.get("news_headlines") or [], ensure_ascii=False
            ) if c.get("news_headlines") else None
            cursor.execute(query, (
                c["stock_code"], c["stock_name"], c["sector"],
                c["current_price"], c["change_pct"],
                c["trading_value"], c["market_cap"],
                c.get("supply_score", 0.0),
                c["inst_net_buy"], c["frgn_net_buy"],
                c["indv_net_buy"], c["prog_net_buy"], c["supply_days"],
                supply_history_json,
                c["ma_aligned"], c["near_high"], hourly_candles_json,
                c["is_leader"], c.get("is_theme_stock", False),
                c.get("content_score", 0),
                c.get("news_count", 0), c.get("news_summary"), news_headlines_json,
                c["score"], c["rank_no"],
            ))
        conn.commit()


def get_stock_report(report_date: str, stock_code: str) -> dict | None:
    """특정 날짜 + 종목 리포트 조회"""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT * FROM daily_stock_report WHERE report_date = %s AND stock_code = %s",
            (report_date, stock_code),
        )
        result = cursor.fetchone()
        if result:
            _serialize_dates(result)
        return result


def get_stock_report_history(stock_code: str, days: int = 3) -> list[dict]:
    """특정 종목의 최근 N일 리포트 조회 (수급 동향용)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM daily_stock_report
               WHERE stock_code = %s
               ORDER BY report_date DESC
               LIMIT %s""",
            (stock_code, days),
        )
        results = cursor.fetchall()
        for row in results:
            _serialize_dates(row)
        return results


def get_stock_reports_by_date(report_date: str) -> list[dict]:
    """특정 날짜의 전체 종목 리포트 목록 (점수순)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT * FROM daily_stock_report
               WHERE report_date = %s
               ORDER BY rank_no ASC""",
            (report_date,),
        )
        results = cursor.fetchall()
        for row in results:
            _serialize_dates(row)
        return results


def get_stock_report_dates(limit: int = 30) -> list[str]:
    """리포트가 존재하는 날짜 목록"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT DISTINCT report_date
               FROM daily_stock_report
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


def save_gap_check_results(report_date: str, rows: list[dict]):
    """갭 체크 결과를 daily_stock_report에 업데이트.

    rows 항목 형태:
      초기(08:10): {rank, now_price, pct}   → gap_nxt_*
      재조회(09:10): {rank, nxt_price?, nxt_pct?, krx_price?, krx_pct?}

    error/pending 행은 가격 값이 없으므로 자연스럽게 건너뜀.
    rank_no는 같은 report_date 안에서 unique 하다고 가정.
    """
    if not rows:
        return

    updates = []
    for r in rows:
        rank = r.get("rank")
        if rank is None:
            continue
        # retry rows use explicit nxt_*/krx_* keys; initial rows use generic now_price/pct (always NXT)
        if any(k in r for k in ("nxt_price", "nxt_pct", "krx_price", "krx_pct")):
            nxt_price = r.get("nxt_price")
            nxt_pct = r.get("nxt_pct")
            krx_price = r.get("krx_price")
            krx_pct = r.get("krx_pct")
        else:
            nxt_price = r.get("now_price")
            nxt_pct = r.get("pct")
            krx_price = None
            krx_pct = None
        if all(v is None for v in (nxt_price, nxt_pct, krx_price, krx_pct)):
            continue
        updates.append((nxt_price, nxt_pct, krx_price, krx_pct, report_date, rank))

    if not updates:
        return

    with get_db() as (conn, cursor):
        for nxt_price, nxt_pct, krx_price, krx_pct, rd, rank in updates:
            cursor.execute(
                """UPDATE daily_stock_report
                   SET gap_nxt_price = COALESCE(%s, gap_nxt_price),
                       gap_nxt_pct   = COALESCE(%s, gap_nxt_pct),
                       gap_krx_price = COALESCE(%s, gap_krx_price),
                       gap_krx_pct   = COALESCE(%s, gap_krx_pct),
                       gap_checked_at = CURRENT_TIMESTAMP
                   WHERE report_date = %s AND rank_no = %s""",
                (nxt_price, nxt_pct, krx_price, krx_pct, rd, rank),
            )
        conn.commit()


def get_gap_stats_by_dates(dates: list[str]) -> dict[str, dict]:
    """여러 날짜의 Top 10 갭 체크 승률 통계를 한 번에 조회.

    반환: {date: {wins, losses, flats, total}}
      - KRX 우선, 없으면 NXT 등락률 기준.
      - 갭 체크가 안 된 날짜는 키 없음.
    """
    if not dates:
        return {}

    placeholders = ",".join(["%s"] * len(dates))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT report_date,
                       COALESCE(gap_krx_pct, gap_nxt_pct) AS pct
                  FROM daily_stock_report
                 WHERE report_date IN ({placeholders})
                   AND rank_no BETWEEN 1 AND 10
                   AND (gap_krx_pct IS NOT NULL OR gap_nxt_pct IS NOT NULL)""",
            tuple(dates),
        )
        rows = cursor.fetchall()

    stats: dict[str, dict] = {}
    for row in rows:
        d = row["report_date"]
        key = d.isoformat() if isinstance(d, (date, datetime)) else str(d)
        pct = row["pct"]
        if pct is None:
            continue
        if isinstance(pct, Decimal):
            pct = float(pct)
        s = stats.setdefault(key, {"wins": 0, "losses": 0, "flats": 0, "total": 0})
        s["total"] += 1
        if pct > 0:
            s["wins"] += 1
        elif pct < 0:
            s["losses"] += 1
        else:
            s["flats"] += 1
    return stats


def get_top_picks_by_dates(dates: list[str]) -> dict[str, dict]:
    """여러 날짜의 1등 종목(rank_no=1)을 한 번에 조회.

    반환: {date: {stock_code, stock_name, score}}
      - 해당 날짜 리포트가 없으면 키 없음.
    """
    if not dates:
        return {}

    placeholders = ",".join(["%s"] * len(dates))
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT report_date, stock_code, stock_name, score
                  FROM daily_stock_report
                 WHERE report_date IN ({placeholders})
                   AND rank_no = 1""",
            tuple(dates),
        )
        rows = cursor.fetchall()

    picks: dict[str, dict] = {}
    for row in rows:
        d = row["report_date"]
        key = d.isoformat() if isinstance(d, (date, datetime)) else str(d)
        score = row["score"]
        if isinstance(score, Decimal):
            score = float(score)
        picks[key] = {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "score": score or 0.0,
        }
    return picks


def _score_to_grade(score: float) -> str:
    """supply_score(0~100) → 등급 문자열. classify_supply_score와 임계값 동일."""
    if score >= 85:
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def build_score_reason(row: dict) -> str:
    """종합 점수 구성요소로 매수 이유 한국어 문구를 조립한다(GPT 미사용).

    closing_bet 의 score_candidate 가중치 항목과 대응한다:
    수급/정배열/신고가/대장주/프로그램/테마/콘텐츠.
    """
    parts: list[str] = []

    score = row.get("score") or 0.0
    parts.append(f"종합 {round(float(score))}점")

    grade = row.get("supply_grade") or _score_to_grade(row.get("supply_score") or 0.0)
    inst = row.get("inst_net_buy") or 0
    frgn = row.get("frgn_net_buy") or 0
    if inst > 0 and frgn > 0:
        subject = "외국인·기관 동반 순매수"
    elif inst > 0:
        subject = "기관 순매수"
    elif frgn > 0:
        subject = "외국인 순매수"
    else:
        subject = ""
    parts.append(f"수급 {grade}등급({subject})" if subject else f"수급 {grade}등급")

    if row.get("is_leader"):
        sector = (row.get("sector") or "").strip()
        parts.append(f"{sector} 대장주" if sector else "섹터 대장주")
    if row.get("is_theme_stock"):
        parts.append("테마 주도주")
    if row.get("ma_aligned"):
        parts.append("정배열")
    if row.get("near_high"):
        parts.append("신고가 근처")
    if (row.get("prog_net_buy") or 0) > 0:
        parts.append("프로그램 순매수")
    if (row.get("content_score") or 0) > 0:
        parts.append("콘텐츠 다수 언급")
    if (row.get("news_count") or 0) > 0:
        parts.append(f"뉴스 재료 {int(row['news_count'])}건")

    return " · ".join(parts)


def _serialize_dates(row: dict):
    """날짜 필드 직렬화 + 점수에서 supply_grade 파생"""
    if isinstance(row.get("report_date"), (date, datetime)):
        row["report_date"] = row["report_date"].isoformat().split("T")[0]
    if isinstance(row.get("created_at"), datetime):
        row["created_at"] = row["created_at"].isoformat()
    if isinstance(row.get("gap_checked_at"), datetime):
        row["gap_checked_at"] = row["gap_checked_at"].isoformat()
    # boolean 변환 (MariaDB TINYINT → Python bool)
    for key in ("ma_aligned", "near_high", "is_leader", "is_theme_stock"):
        if key in row:
            row[key] = bool(row[key])
    # supply_score → supply_grade 파생 (DB에 등급은 저장하지 않음)
    if "supply_score" in row:
        row["supply_grade"] = _score_to_grade(row.get("supply_score") or 0.0)
    # supply_history JSON 파싱
    if "supply_history" in row and isinstance(row["supply_history"], str):
        row["supply_history"] = json.loads(row["supply_history"])
    if row.get("supply_history") is None:
        row["supply_history"] = []
    # hourly_candles JSON 파싱
    if "hourly_candles" in row and isinstance(row["hourly_candles"], str):
        row["hourly_candles"] = json.loads(row["hourly_candles"])
    if row.get("hourly_candles") is None:
        row["hourly_candles"] = []
    # news_headlines JSON 파싱
    if "news_headlines" in row and isinstance(row["news_headlines"], str):
        row["news_headlines"] = json.loads(row["news_headlines"])
    if row.get("news_headlines") is None:
        row["news_headlines"] = []
    # 종합 점수 기반 매수 이유 파생
    if "score" in row:
        row["reason"] = build_score_reason(row)
