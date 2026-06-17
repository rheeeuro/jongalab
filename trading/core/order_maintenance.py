"""미체결 주문 정리 — 개장 시 잔여(전일) 미체결 자동 취소.

시장가 전환 후엔 미체결이 거의 안 생기지만, 세션 마감까지 안 붙어 다음 날까지
남은 우리 주문(데이주문 미소멸 등)을 개장 중 모니터가 취소해 묶임을 막는다.
원주문 거래소(NXT/KRX)를 ka10075 응답에서 읽어 그 거래소로 취소한다.
paper 는 미전송이라 no-op.
"""
import logging

from core.repository import order as order_repo

logger = logging.getLogger("OrderMaint")


def _venue_of(stex_tp_txt: str) -> str:
    t = (stex_tp_txt or "").upper()
    if "NXT" in t:
        return "NXT"
    if "KRX" in t:
        return "KRX"
    return "SOR"


def cancel_stale_orders(client) -> int:
    """전일 이전 미체결(우리 주문)을 취소. 취소/정리한 건수 반환. (live 전용)"""
    if getattr(client, "paper", True):
        return 0
    stale = order_repo.get_stale_sent()
    if not stale:
        return 0

    # 브로커 미체결 맵: ord_no → 거래소
    try:
        oso = client.get_open_orders(stex_tp="0").get("oso", []) or []
    except Exception as e:
        logger.error("미체결 조회 실패 — 정리 보류: %s", e)
        return 0
    venue = {o.get("ord_no"): _venue_of(o.get("stex_tp_txt")) for o in oso}

    n = 0
    for od in stale:
        ono = od["kiwoom_ord_no"]
        if ono in venue:  # 아직 브로커에 미체결로 살아있음 → 취소
            try:
                resp = client.cancel(ono, od["stk_cd"], 0, dmst_stex_tp=venue[ono])
                logger.info("잔여 미체결 취소 [%s] %s: %s",
                            od["stk_cd"], ono, resp.get("return_msg"))
            except Exception as e:
                logger.error("미체결 취소 실패 [%s] %s: %s", od["stk_cd"], ono, e)
                continue
        else:
            logger.info("잔여 미체결 [%s] %s — 브로커에 없음(이미 소멸) → 로컬 정리",
                        od["stk_cd"], ono)
        order_repo.mark_canceled(od["id"])
        n += 1
    return n
