"""레버리지 ETF 대체매수 매핑 데이터 접근.

레버리지 사용(risk_config LEVERAGE_ENABLED)이 켜져 있으면, signal_executor 가 매수 직전
원종목(src_stk_cd)을 여기 매핑된 레버리지 ETF(etf_stk_cd)로 치환한다. 원종목 신호 상태는
그대로 갱신되고, 실제 주문·포지션·청산은 ETF 로 흐른다(사이징은 ETF 현재가로 재계산).
대시보드(PUT /leverage-map)에서 전체 목록을 교체한다. blocklist 패턴을 따른다.
"""
from core.db import get_db


def get_active_map() -> dict[str, dict]:
    """치환 조회용 매핑 {원종목코드: {"etf_cd", "etf_nm"}}. ETF 코드가 있는 행만."""
    with get_db() as (conn, cursor):
        cursor.execute("SELECT src_stk_cd, etf_stk_cd, etf_stk_nm FROM leverage_map")
        return {
            r["src_stk_cd"]: {"etf_cd": r["etf_stk_cd"], "etf_nm": r["etf_stk_nm"]}
            for r in cursor.fetchall()
            if r["etf_stk_cd"]
        }


def get_all() -> list[dict]:
    """매핑 목록 전체 (대시보드용, 최신순)."""
    with get_db() as (conn, cursor):
        cursor.execute(
            "SELECT src_stk_cd, src_stk_nm, etf_stk_cd, etf_stk_nm, created_at "
            "FROM leverage_map ORDER BY created_at DESC"
        )
        return cursor.fetchall()


def replace_all(items: list[dict]) -> list[dict]:
    """매핑 전체 교체. items: [{src_stk_cd, src_stk_nm?, etf_stk_cd, etf_stk_nm?}, ...].
    원종목·ETF 코드가 모두 있어야 유효(둘 중 하나라도 비면 건너뜀)."""
    with get_db() as (conn, cursor):
        cursor.execute("DELETE FROM leverage_map")
        for it in items:
            src = (it.get("src_stk_cd") or "").strip()
            etf = (it.get("etf_stk_cd") or "").strip()
            if not src or not etf:
                continue
            cursor.execute(
                "INSERT INTO leverage_map (src_stk_cd, src_stk_nm, etf_stk_cd, etf_stk_nm) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE src_stk_nm = VALUES(src_stk_nm), "
                "etf_stk_cd = VALUES(etf_stk_cd), etf_stk_nm = VALUES(etf_stk_nm)",
                (src, it.get("src_stk_nm") or None, etf, it.get("etf_stk_nm") or None),
            )
        conn.commit()
    return get_all()
