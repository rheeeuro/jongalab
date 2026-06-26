"""미체결 주문 정리 — 개장 시 잔여(전일) 미체결 자동 취소.

시장가 전환 후엔 미체결이 거의 안 생기지만, 세션 마감까지 안 붙어 다음 날까지
남은 우리 주문(데이주문 미소멸 등)을 개장 중 모니터가 취소해 묶임을 막는다.
원주문 거래소(NXT/KRX)를 ka10075 응답에서 읽어 그 거래소로 취소한다.
paper 는 미전송이라 no-op.
"""
import logging

from core.repository import order as order_repo
from core.repository import fill as fill_repo

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


def reconcile_dead_sent(client) -> int:
    """오늘 전송됐으나 브로커에 없고 체결도 0인 'sent' 주문(소멸한 최유리IOC 등)을 정리. (live 전용)

    `sync_fills` 는 체결(cntr) row 가 있는 주문만 'filled' 로 마감하므로, 0주 체결로 소멸한
    IOC 는 영원히 'sent' 로 남아 멱등키를 물고 같은 tag 재매도를 막는다. 이 함수가 그런
    '죽은' 주문을 canceled 로 마감하고 멱등키를 해제해, 다음 폴링에서 재매도가 가능하게 한다.

    안전 가드: 브로커 미체결(oso)에 아직 살아있는 주문은 체결 여지가 있어 건드리지 않고,
    체결분(fill)이 일부라도 있는 주문은 sync_fills 가 마감하도록 남긴다. 따라서 '브로커에
    없음 + 체결 0' 인 순수 소멸 주문만 정리한다. sync_fills 직후 호출하는 것을 전제로 한다."""
    if getattr(client, "paper", True):
        return 0
    pending = order_repo.get_open_sent()
    if not pending:
        return 0
    try:
        oso = client.get_open_orders(stex_tp="0").get("oso", []) or []
    except Exception as e:
        logger.error("미체결 조회 실패 — 죽은주문 정리 보류: %s", e)
        return 0
    live = {o.get("ord_no") for o in oso}

    n = 0
    for od in pending:
        ono = od["kiwoom_ord_no"]
        if ono in live:
            continue  # 아직 브로커에 살아있음(체결 여지) → 보존
        if fill_repo.filled_qty(od["id"]) > 0:
            continue  # 부분체결 존재 → sync_fills 가 마감 처리
        order_repo.void_dead_order(od["id"])
        logger.info("죽은 주문 정리 [%s] %s — 브로커에 없음+체결0 → canceled+멱등키 해제(재매도 허용)",
                    od["stk_cd"], ono)
        n += 1
    return n
