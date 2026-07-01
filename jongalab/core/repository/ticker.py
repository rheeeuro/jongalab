"""티커 사전 데이터 접근"""
from datetime import datetime

from core.db import get_db


def lookup_ticker(company_name: str) -> dict | None:
    """ticker_dictionary에서 기업명으로 티커 조회 (ACTIVE 우선, PENDING도 허용)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT id, company_name, ticker_symbol, status
            FROM ticker_dictionary
            WHERE company_name = %s
            ORDER BY FIELD(status, 'ACTIVE', 'PENDING', 'INACTIVE')
            LIMIT 1
            """,
            (company_name,),
        )
        return cursor.fetchone()


def lookup_name_by_ticker(ticker_symbol: str) -> str | None:
    """ticker_dictionary에서 티커 심볼로 기업명 조회 (ACTIVE 우선)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            SELECT company_name FROM ticker_dictionary
            WHERE ticker_symbol = %s AND status != 'INACTIVE'
            ORDER BY FIELD(status, 'ACTIVE', 'PENDING')
            LIMIT 1
            """,
            (ticker_symbol,),
        )
        row = cursor.fetchone()
        return row["company_name"] if row else None


def save_ticker(company_name: str, ticker_symbol: str, status: str = "PENDING") -> None:
    """ticker_dictionary에 새 항목 추가 (중복이면 무시)"""
    with get_db() as (conn, cursor):
        cursor.execute(
            """
            INSERT IGNORE INTO ticker_dictionary (company_name, ticker_symbol, status)
            VALUES (%s, %s, %s)
            """,
            (company_name, ticker_symbol, status),
        )
        conn.commit()


def bulk_upsert_active_tickers(rows: list[dict]) -> int:
    """상장종목 리스트를 ticker_dictionary 에 ACTIVE 로 일괄 업서트 (뉴스 시딩 워커용).

    rows 항목: {company_name, ticker_symbol}
    - 신규는 ACTIVE 로 삽입.
    - 기존 행은 티커를 최신으로 갱신하되, 관리자가 INACTIVE 로 꺼둔 종목은 건드리지 않는다.
      (PENDING → ACTIVE 로 승격, sector 캐시는 유지)
    반환: 영향받은 행 수(삽입/갱신 합).
    """
    if not rows:
        return 0
    with get_db() as (conn, cursor):
        cursor.executemany(
            """
            INSERT INTO ticker_dictionary (company_name, ticker_symbol, status)
            VALUES (%(company_name)s, %(ticker_symbol)s, 'ACTIVE')
            ON DUPLICATE KEY UPDATE
                ticker_symbol = VALUES(ticker_symbol),
                status = IF(status = 'INACTIVE', 'INACTIVE', 'ACTIVE')
            """,
            rows,
        )
        affected = cursor.rowcount
        conn.commit()
    return affected


def get_ticker_dictionary(status: str | None = None) -> list[dict]:
    """ticker_dictionary 전체 조회. status 필터 가능"""
    with get_db() as (conn, cursor):
        conditions: list[str] = []
        params: list[str] = []
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        order = "updated_at DESC" if conditions else "FIELD(status, 'PENDING', 'ACTIVE', 'INACTIVE'), updated_at DESC"
        cursor.execute(f"SELECT * FROM ticker_dictionary{where} ORDER BY {order}", params)

        results = cursor.fetchall()
        for row in results:
            for col in ("created_at", "updated_at", "sector_updated_at"):
                if isinstance(row.get(col), datetime):
                    row[col] = row[col].isoformat()
        return results


def update_ticker(
    ticker_id: int,
    company_name: str,
    ticker_symbol: str,
    status: str,
    sector: str | None = None,
) -> bool:
    """ticker_dictionary 항목 수정.
    sector가 None이 아니면 sector + sector_updated_at도 함께 갱신
    (관리자 수동 변경분이 resolver에 덮이지 않도록 TTL 리셋).
    """
    sets = ["company_name = %s", "ticker_symbol = %s", "status = %s"]
    params: list = [company_name, ticker_symbol, status]
    if sector is not None:
        sets.append("sector = %s")
        sets.append("sector_updated_at = CURRENT_TIMESTAMP")
        params.append(sector or None)
    params.append(ticker_id)
    sql = f"UPDATE ticker_dictionary SET {', '.join(sets)} WHERE id = %s"
    with get_db() as (conn, cursor):
        cursor.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0


def delete_ticker(ticker_id: int) -> bool:
    """ticker_dictionary 항목 삭제"""
    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM ticker_dictionary WHERE id = %s", (ticker_id,))
        conn.commit()
        return cursor.rowcount > 0
