"""체결 기록 — 키움 체결 통보/조회로 갱신, 포지션 산출의 근거."""
from core.db import get_db


def record_fill(order_id: int, stk_cd: str, qty: int, price: int,
                cmsn: int = 0, tax: int = 0) -> int:
    """체결 1건 기록. 생성된 fill id 반환.

    cmsn/tax 는 이 체결분(증분)의 매매수수료·세금(원). live 는 키움 ka10076
    (tdy_trde_cmsn/tdy_trde_tax)에서 채우고, paper(execution_engine)는 기본 0.
    """
    with get_db() as (conn, cursor):
        cursor.execute(
            "INSERT INTO fill (order_id, stk_cd, qty, price, cmsn, tax) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (order_id, stk_cd, qty, price, cmsn, tax),
        )
        conn.commit()
        return cursor.lastrowid


def filled_qty(order_id: int) -> int:
    """해당 주문에 대해 지금까지 기록된 체결 수량 합 (live 동기화 멱등용)."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT COALESCE(SUM(qty), 0) AS q FROM fill WHERE order_id = %s", (order_id,))
        return int(cursor.fetchone()["q"])


def recorded_fees(order_id: int) -> dict:
    """해당 주문에 지금까지 기록된 수수료·세금 합 (live 동기화 증분 계산용)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COALESCE(SUM(cmsn), 0) AS c, COALESCE(SUM(tax), 0) AS t "
            "FROM fill WHERE order_id = %s",
            (order_id,),
        )
        row = cursor.fetchone()
        return {"cmsn": int(row["c"]), "tax": int(row["t"])}


def fees_by_date(date_dash: str) -> dict:
    """해당 날짜(YYYY-MM-DD) 체결의 수수료·세금 합계 — 대시보드 표시용."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT COALESCE(SUM(cmsn), 0) AS c, COALESCE(SUM(tax), 0) AS t "
            "FROM fill WHERE DATE(filled_at) = %s",
            (date_dash,),
        )
        row = cursor.fetchone()
        c, t = int(row["c"]), int(row["t"])
        return {"cmsn": c, "tax": t, "total": c + t}


def get_fills_by_order(order_id: int) -> list[dict]:
    with get_db() as (conn, cursor):
        cursor.execute("SELECT * FROM fill WHERE order_id = %s", (order_id,))
        return cursor.fetchall()
