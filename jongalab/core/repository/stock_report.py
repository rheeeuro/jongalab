"""종목일간리포트 데이터 접근"""
import json
from datetime import date, datetime
from decimal import Decimal

from core.db import get_db


# 시간 창에서만 수집되는 스냅샷 캡처 컬럼의 upsert 정책 (2026-07-19, 프로그램 오전/오후 분해):
#  · prog_am_net — 정오 창(12:00~12:45) 실행의 첫 캡처를 보존(first-write-wins).
#    이후 실행(오후·저녁)은 None 을 보내며, 값이 이미 있으면 갱신하지 않는다.
#  · prog_pm_net — 오후 창 실행이 갱신(last-write-wins)하되 창 밖 실행의 NULL 은 무시.
_FIRST_WRITE_WINS = frozenset({"prog_am_net"})
#  · ob_* — 호가 미시구조는 연속장 중에만 유효(장 종료 후 잔량 0→파생값 None). 세션 중
#    마지막 실행(종가 직전 ~15시)이 last-write-wins 로 남고, 장 종료 후 재실행의 NULL 은
#    무시해 근사 '매수 당시' 스냅샷을 보존한다.
#  · news_* 재료 지속성 라벨 — LLM 판정은 새 헤드라인이 있을 때만 재호출하므로(비용·처리량),
#    판정을 건너뛴 실행이나 LLM 실패는 None 을 보낸다. 그때 그날의 판정이 지워지면 안 된다.
#    (정상 경로에서는 closing_bet 이 기존 라벨을 읽어 in-memory 로도 이어붙인다 — rule 평가가
#     메모리 dict 를 보므로 캐리포워드가 필수고, 이 집합은 DB 쪽 백스톱이다.)
#    ⚠️ LLM 라벨 컬럼은 **하나도 빠짐없이** 이 집합과 _NEWS_LABEL_COLS 양쪽에 있어야 한다.
#    2026-07-29 첫 실행에서 news_summary/news_sentiment/news_catalyst 를 빼먹어, 캐시 스킵
#    실행이 그 3개만 NULL 로 덮었다(4축은 살아남아 한 행 안에서 라벨이 어긋났다).
_PRESERVE_ON_NULL = frozenset({
    "prog_pm_net", "ob_imbalance", "ob_fpr_imbalance", "ob_spread_pct",
    "news_summary", "news_sentiment", "news_catalyst",
    "news_next_milestone", "news_amount_locked", "news_driver_scope", "news_stage",
    "news_durability", "news_label_reason", "news_judge_max_at",
})


def _analysis_row(c: dict) -> dict:
    """후보 dict → daily_stock_report 의 '분석 컬럼' 한 행 (컬럼명 → 값).

    **이 dict 의 키가 분석 컬럼 목록의 단일 소스다.** 컬럼을 추가할 땐 여기 한 곳만 고치면
    INSERT/UPDATE 문이 따라온다(save_stock_reports 가 키에서 파생). 예전엔 컬럼 목록과 값
    dict 를 따로 나열해서, 한쪽만 고치면 저장이 통째로 깨졌다(2026-07-28 disc_* 3종 누락으로
    하루치 리포트 유실).

    closing_bet 이 매 실행 재계산하는 컬럼만 담는다. 다른 워커가 같은 날 행에 쓰는 관측 컬럼
    (krx_close_price·nxt_price_1950·nxt_gap_pct·nxt_after_value·nxt_listed 등)은 여기
    없으므로 재실행에도 보존된다.
    """
    return {
        "stock_code": c["stock_code"],
        "stock_name": c["stock_name"],
        "sector": c["sector"],
        "current_price": c["current_price"],
        "change_pct": c["change_pct"],
        "trading_value": c["trading_value"],
        "market_cap": c["market_cap"],
        "supply_score": c.get("supply_score", 0.0),
        "inst_net_buy": c["inst_net_buy"],
        "frgn_net_buy": c["frgn_net_buy"],
        "indv_net_buy": c["indv_net_buy"],
        "prog_net_buy": c["prog_net_buy"],
        "supply_days": c["supply_days"],
        "supply_history": json.dumps(
            c.get("supply_history", []), ensure_ascii=False
        ) if c.get("supply_history") else None,
        "ma_aligned": c["ma_aligned"],
        "near_high": c["near_high"],
        "hourly_candles": json.dumps(
            c.get("hourly_candles", []), ensure_ascii=False
        ) if c.get("hourly_candles") else None,
        "is_leader": c["is_leader"],
        "is_theme_stock": c.get("is_theme_stock", False),
        "content_score": c.get("content_score", 0),
        "news_count": c.get("news_count", 0),
        "news_unique_count": c.get("news_unique_count", 0),
        "news_pm_count": c.get("news_pm_count", 0),
        "news_first_today": c.get("news_first_today", 0),
        "news_prior_avg": c.get("news_prior_avg"),
        "news_summary": c.get("news_summary"),
        "news_sentiment": c.get("news_sentiment"),
        "news_catalyst": c.get("news_catalyst"),
        # 재료 지속성 라벨 (sql/40) — LLM 사실 4축 + 코드 합성 등급 + 판정 근거·캐시 기준.
        # 전부 _PRESERVE_ON_NULL 대상(판정 스킵/실패의 NULL 이 그날 판정을 지우지 않는다).
        "news_next_milestone": c.get("news_next_milestone"),
        "news_amount_locked": c.get("news_amount_locked"),
        "news_driver_scope": c.get("news_driver_scope"),
        "news_stage": c.get("news_stage"),
        "news_durability": c.get("news_durability"),
        "news_label_reason": c.get("news_label_reason"),
        "news_judge_max_at": c.get("news_judge_max_at"),
        "news_headlines": json.dumps(
            c.get("news_headlines") or [], ensure_ascii=False
        ) if c.get("news_headlines") else None,
        "disc_count": c.get("disc_count"),
        "disc_bad_type": c.get("disc_bad_type"),
        "disc_good_type": c.get("disc_good_type"),
        "score": c["score"],
        "rank_no": c["rank_no"],
        "selected": c.get("selected", 1),
        # 선정 근거(sql/43) — selected 와 한 몸으로 매 실행 재판정된다. hybrid/rules 모드에서
        # 매칭된 live selector rule name 콤마 목록, 점수순 선정·비선정은 None.
        # ⚠️ _PRESERVE_ON_NULL 에 넣지 말 것: legacy 폴백 실행의 None 은 '그 실행은 점수순
        #   선정이었다'는 사실이라, 이전 실행의 rule 태그를 남겨두면 화면이 거짓말을 한다.
        "rule_names": c.get("rule_names"),
        "sector_rel_ret": c.get("sector_rel_ret"),
        "sector_leader_chg": c.get("sector_leader_chg"),
        "foreign_brokers_buying": c.get("foreign_brokers_buying"),
        "afternoon_ret": c.get("afternoon_ret"),
        "vol_ratio": c.get("vol_ratio"),
        "prog_buy_days": c.get("prog_buy_days"),
        "first_seen": c.get("first_seen"),
        "theme_strength": c.get("theme_strength"),
        "frgn_exhaust_rate": c.get("frgn_exhaust_rate"),
        "frgn_exhaust_chg": c.get("frgn_exhaust_chg"),
        "is_bio": c.get("is_bio"),
        "market": c.get("market"),
        "dist_prior_high_pct": c.get("dist_prior_high_pct"),
        "round_dist_pct": c.get("round_dist_pct"),
        "ma5_reclaim": c.get("ma5_reclaim"),
        "days_since_frgn_surge": c.get("days_since_frgn_surge"),
        "red_candle": c.get("red_candle"),
        "red_candle_streak": c.get("red_candle_streak"),
        "overhead_vol_ratio": c.get("overhead_vol_ratio"),
        "poc_dist_pct": c.get("poc_dist_pct"),
        "prog_am_net": c.get("prog_am_net"),
        "prog_pm_net": c.get("prog_pm_net"),
        "fin_per": c.get("fin_per"),
        "fin_pbr": c.get("fin_pbr"),
        "fin_ev": c.get("fin_ev"),
        "fin_roe": c.get("fin_roe"),
        "fin_eps": c.get("fin_eps"),
        "fin_bps": c.get("fin_bps"),
        "fin_sales": c.get("fin_sales"),
        "fin_op_profit": c.get("fin_op_profit"),
        "fin_net_income": c.get("fin_net_income"),
        "op_earnings_yield": c.get("op_earnings_yield"),
        "ob_imbalance": c.get("ob_imbalance"),
        "ob_fpr_imbalance": c.get("ob_fpr_imbalance"),
        "ob_spread_pct": c.get("ob_spread_pct"),
    }


def save_stock_reports(candidates: list[dict]):
    """Phase 2 결과를 upsert 저장 — 분석 컬럼만 갱신, 관측 컬럼은 보존.

    closing_bet 은 08:00~20:30 매 30분 재실행된다. 예전 DELETE+INSERT 방식은 19:50 NXT
    스냅샷(gap_check --base-nxt 가 쓴 nxt_listed 등)을 20:00 이후 실행이 매일 지웠다.
    이번 배치에서 빠진 종목(후보 탈락)은 삭제해 '당일 행 = 최신 배치 유니버스' 의미는 유지한다.

    컬럼 목록은 _analysis_row 의 키에서 파생한다 — 목록을 따로 두지 않으므로 어긋날 수 없다.
    """
    if not candidates:
        return

    rows = [_analysis_row(c) for c in candidates]
    col_names = tuple(rows[0])

    # upsert 정책 집합은 컬럼명을 문자열로 참조하는 유일한 곳 — 오타·리네임이 나면 정책이
    # 조용히 무력화(예: prog_am_net 이 정오 캡처를 덮어씀)되므로 이름 유효성을 확인한다.
    unknown = (_FIRST_WRITE_WINS | _PRESERVE_ON_NULL) - set(col_names)
    if unknown:
        raise KeyError(f"upsert 정책에만 있고 분석 컬럼에 없는 이름: {sorted(unknown)}")

    cols = ", ".join(col_names)
    placeholders = ", ".join(["%s"] * len(col_names))
    updates = ", ".join(
        f"{c} = COALESCE({c}, VALUES({c}))" if c in _FIRST_WRITE_WINS
        else f"{c} = COALESCE(VALUES({c}), {c})" if c in _PRESERVE_ON_NULL
        else f"{c} = VALUES({c})"
        for c in col_names
    )
    query = f"""
        INSERT INTO daily_stock_report (report_date, {cols})
        VALUES (CURDATE(), {placeholders})
        ON DUPLICATE KEY UPDATE {updates}
    """

    with get_db() as (conn, cursor):
        code_ph = ", ".join(["%s"] * len(candidates))
        cursor.execute(
            f"""DELETE FROM daily_stock_report
                 WHERE report_date = CURDATE() AND stock_code NOT IN ({code_ph})""",
            tuple(r["stock_code"] for r in rows),
        )

        for row in rows:
            cursor.execute(query, tuple(row[col] for col in col_names))
        conn.commit()


def get_recent_report_codes(days: int = 14) -> set[str]:
    """직전 days 일(오늘 제외) 리포트에 등장한 종목코드 집합 — first_seen 피처 파생용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT DISTINCT stock_code FROM daily_stock_report
               WHERE report_date < CURDATE()
                 AND report_date >= CURDATE() - INTERVAL %s DAY""",
            (int(days),),
        )
        return {r["stock_code"] for r in cursor.fetchall()}


def get_today_prog_am_map() -> dict[str, int]:
    """당일 행에 저장된 종목코드 → 정오 프로그램 누적 순매수(prog_am_net) 맵.

    closing_bet 오후 실행이 prog_pm_net(현재 누적 − 정오 누적) 차분에 사용한다.
    정오 창 실행이 아직 안 돌았거나 그때 유니버스에 없던 종목은 맵에 없다(피처 결측)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT stock_code, prog_am_net FROM daily_stock_report
               WHERE report_date = CURDATE() AND prog_am_net IS NOT NULL"""
        )
        return {r["stock_code"]: int(r["prog_am_net"]) for r in cursor.fetchall()}


def get_prev_frgn_exhaust_map() -> dict[str, float]:
    """직전 리포트 거래일의 종목코드 → 외인소진율 맵 — frgn_exhaust_chg 피처 파생용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT stock_code, frgn_exhaust_rate FROM daily_stock_report
               WHERE report_date = (SELECT MAX(report_date) FROM daily_stock_report
                                     WHERE report_date < CURDATE())
                 AND frgn_exhaust_rate IS NOT NULL"""
        )
        return {r["stock_code"]: float(r["frgn_exhaust_rate"]) for r in cursor.fetchall()}


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


def get_stock_reports_by_date(report_date: str, include_unselected: bool = False) -> list[dict]:
    """특정 날짜의 종목 리포트 목록 (점수순).

    기본은 selected=1(실매매 핸드오프된 상위 종목)만 — 기존 소비자(대시보드·gap_check)의
    동작을 그대로 유지한다. include_unselected=True 면 비선정 후보까지 유니버스 전체(엣지 연구용).
    """
    cond = "" if include_unselected else " AND selected = 1"
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT * FROM daily_stock_report
               WHERE report_date = %s{cond}
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


def save_nxt_snapshot(report_date: str, rows: list[dict]):
    """19:50 NXT 스냅샷을 daily_stock_report 에 UPDATE (upsert 아님 — 리포트 행이 이미 존재).

    rows 항목: {stock_code, krx_close_price, nxt_price_1950, nxt_gap_pct,
                nxt_after_value, nxt_listed}. None 값은 COALESCE 로 기존 값 보존.
    stock_code(6자리) 기준으로 매칭 — closing_bet 저장 코드와 동일 형식.
    """
    if not rows:
        return
    with get_db() as (conn, cursor):
        for r in rows:
            code = r.get("stock_code")
            if not code:
                continue
            cursor.execute(
                """UPDATE daily_stock_report
                   SET krx_close_price = COALESCE(%s, krx_close_price),
                       nxt_price_1950  = COALESCE(%s, nxt_price_1950),
                       nxt_gap_pct     = COALESCE(%s, nxt_gap_pct),
                       nxt_after_value = COALESCE(%s, nxt_after_value),
                       nxt_listed      = COALESCE(%s, nxt_listed)
                   WHERE report_date = %s AND stock_code = %s""",
                (
                    r.get("krx_close_price"), r.get("nxt_price_1950"),
                    r.get("nxt_gap_pct"), r.get("nxt_after_value"),
                    r.get("nxt_listed"), report_date, code,
                ),
            )
        conn.commit()


def get_gap_stats_by_dates(dates: list[str]) -> dict[str, dict]:
    """여러 날짜의 선정 종목 갭 체크 승률 통계를 한 번에 조회.

    반환: {date: {wins, losses, flats, total}}
      - KRX 우선, 없으면 NXT 등락률 기준.
      - 갭 체크가 안 된 날짜는 키 없음.
      - 모집단은 **selected=1**(그날 리포트에 실린 종목 = gap_check 대상). rank_no 로
        자르면 안 된다 — hybrid/rules 모드의 룰 선정 종목은 점수 순위가 10위 밖이라
        리포트에는 있는데 승패 집계에서 빠져 캘린더와 리포트가 어긋난다(2026-07-30 수정).
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
                   AND selected = 1
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
    for key in ("ma_aligned", "near_high", "is_leader", "is_theme_stock", "news_first_today"):
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


def get_report_dates_before_today() -> list[str]:
    """과거(오늘 제외) report_date 전체(오래된→최신) — rule_evaluator catch-up 채점 후보용.

    get_stock_report_dates(최신순·limit)와 달리 상한 없이 전체를 오름차순으로 준다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT DISTINCT report_date FROM daily_stock_report
                WHERE report_date < CURDATE() ORDER BY report_date ASC"""
        )
        return [
            r["report_date"].isoformat() if hasattr(r["report_date"], "isoformat")
            else str(r["report_date"])
            for r in cursor.fetchall()
        ]


# ── 엣지 연구용 결과 백필 (outcome_backfill 워커) ──
# 일봉 백필 라벨 4종(같은 일봉 1회 조회에서 파생). nxt_open_ret 은 실시간 수집이라 별도.
_OUTCOME_LABELS = ("next_open_ret", "next_high_ret", "next_low_ret", "next_close_ret")
_OUTCOME_MISSING_COND = " OR ".join(f"{c} IS NULL" for c in _OUTCOME_LABELS)


def get_dates_missing_outcome(min_date: str | None = None) -> list[str]:
    """일봉 라벨 4종 중 하나라도 안 채워진 행이 있는 report_date 목록(오래된→최신).

    min_date(YYYY-MM-DD) 이후만. 오늘 날짜는 '다음 거래일'이 아직 없으므로 제외한다.
    """
    with get_db() as (conn, cursor):
        params: list = []
        cond = f"({_OUTCOME_MISSING_COND}) AND report_date < CURDATE()"
        if min_date:
            cond += " AND report_date >= %s"
            params.append(min_date)
        cursor.execute(
            f"""SELECT DISTINCT report_date FROM daily_stock_report
                 WHERE {cond} ORDER BY report_date ASC""",
            tuple(params),
        )
        rows = cursor.fetchall()
    return [
        r["report_date"].isoformat() if isinstance(r["report_date"], (date, datetime))
        else str(r["report_date"])
        for r in rows
    ]


def get_rows_missing_outcome(report_date: str) -> list[dict]:
    """특정 report_date 에서 일봉 라벨 4종 중 하나라도 비어있는 행 목록.

    반환: stock_code·current_price + 라벨 4종(이미 채워진 라벨은 COALESCE 로 보존되므로
    호출부는 전부 재계산해 넘겨도 무방).
    """
    labels = ", ".join(_OUTCOME_LABELS)
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT stock_code, current_price, {labels} FROM daily_stock_report
                WHERE report_date = %s AND ({_OUTCOME_MISSING_COND})""",
            (report_date,),
        )
        return cursor.fetchall()


def save_outcome_labels(report_date: str, results: list[dict]) -> int:
    """일봉 결과 라벨 백필. results: [{stock_code, next_open_ret, next_high_ret,
    next_low_ret, next_close_ret}]. None 라벨은 COALESCE 로 기존 값 보존(멱등). 갱신 행 수 반환.
    """
    if not results:
        return 0
    sets = ", ".join(f"{c} = COALESCE(%s, {c})" for c in _OUTCOME_LABELS)
    n = 0
    with get_db() as (conn, cursor):
        for r in results:
            cursor.execute(
                f"""UPDATE daily_stock_report SET {sets}
                    WHERE report_date = %s AND stock_code = %s""",
                (*(r.get(c) for c in _OUTCOME_LABELS), report_date, r["stock_code"]),
            )
            n += cursor.rowcount
        conn.commit()
    return n


def save_next_open_ret(report_date: str, results: list[dict]) -> int:
    """하위호환 shim — 단일 next_open_ret 만 담긴 results 를 save_outcome_labels 로 위임."""
    return save_outcome_labels(report_date, results)


def save_nxt_open_labels(report_date: str, rows: list[dict]) -> int:
    """08:06 NXT 프리마켓 라벨 UPDATE. rows: [{stock_code, nxt_open_price, nxt_open_ret}].
    None 은 COALESCE 로 기존 값 보존. 갱신 행 수 반환.
    """
    if not rows:
        return 0
    n = 0
    with get_db() as (conn, cursor):
        for r in rows:
            cursor.execute(
                """UPDATE daily_stock_report
                   SET nxt_open_price = COALESCE(%s, nxt_open_price),
                       nxt_open_ret   = COALESCE(%s, nxt_open_ret)
                   WHERE report_date = %s AND stock_code = %s""",
                (r.get("nxt_open_price"), r.get("nxt_open_ret"), report_date, r["stock_code"]),
            )
            n += cursor.rowcount
        conn.commit()
    return n


# ── 시간외 반응 + 리스크 라벨 (after_hours_labels 워커, 18:05) ──
_AFTER_HOURS_COLS = (
    "ah_price", "ah_flu_rt", "ah_volume", "ah_react",
    "credit_remn_rt", "short_wght", "short_wght_5d",
    "lend_remn", "lend_irds_5d", "exec_str", "exec_str_5d",
)


def get_report_codes(report_date: str) -> list[str]:
    """특정 report_date 유니버스의 종목코드 목록(rank 순) — 시간외/리스크 라벨 수집 대상."""
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT stock_code FROM daily_stock_report
                WHERE report_date = %s ORDER BY rank_no ASC""",
            (report_date,),
        )
        return [r["stock_code"] for r in cursor.fetchall()]


def save_after_hours_labels(report_date: str, rows: list[dict]) -> int:
    """시간외단일가·리스크 라벨 UPDATE (관측 컬럼 — closing_bet upsert 와 분리, 멱등).

    rows: [{stock_code, <_AFTER_HOURS_COLS...>}]. None 은 COALESCE 로 기존 값 보존.
    """
    if not rows:
        return 0
    sets = ", ".join(f"{c} = COALESCE(%s, {c})" for c in _AFTER_HOURS_COLS)
    n = 0
    with get_db() as (conn, cursor):
        for r in rows:
            cursor.execute(
                f"""UPDATE daily_stock_report SET {sets}
                    WHERE report_date = %s AND stock_code = %s""",
                (*(r.get(c) for c in _AFTER_HOURS_COLS), report_date, r["stock_code"]),
            )
            n += cursor.rowcount
        conn.commit()
    return n


# ── 뉴스 재료 지속성 라벨 (closing_bet 판정 캐시 + outcome_backfill 채점) ──

# LLM 이 한 번의 판정으로 함께 만드는 라벨 전부 — 요약·방향·유형도 같은 호출 산출물이므로
# 캐리포워드 대상이다(빠지면 캐시 스킵 실행이 그 컬럼만 지워 한 행 안에서 라벨이 어긋난다).
_NEWS_LABEL_COLS = (
    "news_summary", "news_sentiment", "news_catalyst",
    "news_next_milestone", "news_amount_locked", "news_driver_scope", "news_stage",
    "news_durability", "news_label_reason", "news_judge_max_at",
)


def get_today_news_labels(stock_codes: list[str]) -> dict[str, dict]:
    """오늘 행에 이미 있는 재료 지속성 라벨 — 재판정 스킵 판단 + in-memory 캐리포워드용.

    closing_bet 은 30분마다 재실행되고 rule 평가는 **메모리 dict** 를 보므로, 판정을 건너뛴
    실행에서도 라벨이 행에 실려 있어야 veto/selector 가 같은 판단을 한다.
    반환: {code: {<_NEWS_LABEL_COLS...>}}
    """
    codes = [c.split("_")[0].split(".")[0] for c in stock_codes if c]
    if not codes:
        return {}
    placeholders = ", ".join(["%s"] * len(codes))
    cols = ", ".join(_NEWS_LABEL_COLS)
    with get_db() as (conn, cursor):
        cursor.execute(
            f"""SELECT stock_code, {cols} FROM daily_stock_report
                 WHERE report_date = CURDATE() AND stock_code IN ({placeholders})""",
            tuple(codes),
        )
        return {r.pop("stock_code"): r for r in cursor.fetchall()}


def get_news_material_rows(report_date: str) -> list[dict]:
    """그 날 뉴스가 있던 유니버스 행의 **재료 라벨 슬림 목록** (뉴스 화면·탭용).

    `get_stock_reports_by_date` 는 SELECT * 라 hourly_candles·supply_history 같은 무거운 JSON
    까지 실어 목록 화면에는 과하다. 비선정(selected=0) 후보도 포함한다 — 뉴스 화면은 '오늘 뜬
    재료' 전체를 보여주는 곳이고, 매매 선정 여부와 축이 다르다.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT stock_code, stock_name, sector, change_pct, market_cap, trading_value,
                      rank_no, selected, score,
                      news_count, news_unique_count, news_pm_count, news_first_today,
                      news_prior_avg, news_summary, news_sentiment, news_catalyst,
                      news_next_milestone, news_amount_locked, news_driver_scope,
                      news_stage, news_durability, news_label_reason, news_followup_days
                 FROM daily_stock_report
                WHERE report_date = %s AND news_count > 0
                ORDER BY rank_no ASC""",
            (report_date,),
        )
        return cursor.fetchall()


def get_rows_for_news_followup(window_days: int) -> list[dict]:
    """후속 재료 채점 대상 — 지속성 라벨이 있고 채점 창이 아직 열려 있는 과거 행.

    창이 닫힌(리포트일 + window_days 가 지난) 행은 값이 확정되므로 다시 계산하지 않는다.
    창이 열려 있는 동안은 매 실행 재계산(멱등) — 날짜 수는 창이 자라며 단조 증가한다.
    news_mention 보존이 14일이므로 창을 14일 넘게 잡으면 앞쪽 표본이 잘린다(config 주석 참조).
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT report_date, stock_code FROM daily_stock_report
                WHERE news_durability IS NOT NULL
                  AND report_date < CURDATE()
                  AND report_date >= CURDATE() - INTERVAL %s DAY
                ORDER BY report_date ASC""",
            (int(window_days),),
        )
        return cursor.fetchall()


def save_news_followup(rows: list[dict]) -> int:
    """news_followup_days UPDATE. rows: [{report_date, stock_code, news_followup_days}]."""
    if not rows:
        return 0
    n = 0
    with get_db() as (conn, cursor):
        for r in rows:
            cursor.execute(
                """UPDATE daily_stock_report SET news_followup_days = %s
                    WHERE report_date = %s AND stock_code = %s""",
                (r["news_followup_days"], r["report_date"], r["stock_code"]),
            )
            n += cursor.rowcount
        conn.commit()
    return n


# ── 엣지 연구용 실집행 레그 라벨 (outcome_backfill 워커) ──
# exec_leg_ret 은 종목별 실제 청산 venue 창을 하나로 접은 라벨이다.
#   NXT: 전일 19:50 NXT → 익일 08:03 NXT
#   KRX: 전일 15:20 KRX → 익일 09:03 KRX


def get_dates_missing_exec_leg(min_date: str | None = None) -> list[str]:
    """exec_leg_ret 이 비어있는 행이 있는 report_date 목록(오래된→최신).

    오늘 날짜는 익일 청산 시각이 아직 없으므로 제외한다.
    """
    with get_db() as (conn, cursor):
        params: list = []
        cond = "exec_leg_ret IS NULL AND report_date < CURDATE()"
        if min_date:
            cond += " AND report_date >= %s"
            params.append(min_date)
        cursor.execute(
            f"""SELECT DISTINCT report_date FROM daily_stock_report
                 WHERE {cond} ORDER BY report_date ASC""",
            tuple(params),
        )
        rows = cursor.fetchall()
    return [
        r["report_date"].isoformat() if isinstance(r["report_date"], (date, datetime))
        else str(r["report_date"])
        for r in rows
    ]


def get_rows_missing_exec_leg(report_date: str) -> list[dict]:
    """특정 report_date 에서 실집행 레그 라벨이 비어있는 행 목록.

    `krx_close_price`(그날 실거래 KRX 확정 종가, 미조정)를 함께 준다 — 백필이 수정주가 일봉
    종가와 비교해 권리락을 감지하는 데 쓴다(core.daily_ohlc `is_price_scale_shifted`).
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            """SELECT stock_code, stock_name, nxt_listed, exec_leg_ret, exec_leg_venue,
                      krx_close_price
                 FROM daily_stock_report
                WHERE report_date = %s AND exec_leg_ret IS NULL
                ORDER BY rank_no ASC""",
            (report_date,),
        )
        return cursor.fetchall()


def clear_nxt_open_labels(report_date: str, stock_codes: list[str]) -> int:
    """08:06 NXT 프리마켓 라벨(nxt_open_price·nxt_open_ret)을 NULL 로 되돌린다.

    권리락 종목 전용 — gap_check 는 08:06 시점에 권리락을 구분할 수 없어(전일 종가 대비
    기계적 -N% 가 실제 급락과 구별되지 않는다) 일단 저장하고, 일봉을 이미 들고 있는
    outcome_backfill 이 스케일 가드로 감지해 여기서 지운다. 삭제 행 수 반환.
    """
    if not stock_codes:
        return 0
    n = 0
    with get_db() as (conn, cursor):
        for code in stock_codes:
            cursor.execute(
                """UPDATE daily_stock_report
                      SET nxt_open_price = NULL, nxt_open_ret = NULL
                    WHERE report_date = %s AND stock_code = %s
                      AND (nxt_open_price IS NOT NULL OR nxt_open_ret IS NOT NULL)""",
                (report_date, code),
            )
            n += cursor.rowcount
        conn.commit()
    return n


def save_exec_leg_labels(report_date: str, results: list[dict]) -> int:
    """실집행 레그 라벨 백필. results: [{stock_code, exec_leg_ret, exec_leg_venue}].

    None 값은 COALESCE 로 기존 값 보존(멱등). 갱신 행 수 반환.
    """
    if not results:
        return 0
    n = 0
    with get_db() as (conn, cursor):
        for r in results:
            cursor.execute(
                """UPDATE daily_stock_report
                   SET exec_leg_ret = COALESCE(%s, exec_leg_ret),
                       exec_leg_venue = COALESCE(%s, exec_leg_venue)
                 WHERE report_date = %s AND stock_code = %s""",
                (r.get("exec_leg_ret"), r.get("exec_leg_venue"), report_date, r["stock_code"]),
            )
            n += cursor.rowcount
        conn.commit()
    return n

