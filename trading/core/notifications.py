"""텔레그램 알림 — trading 관리자 전송 (매수 현황 등).

ADMIN chat id 는 jongalab DB(telegram_users)에서 읽고, jongalab 과 동일한
TELEGRAM_TOKEN 으로 전송한다. 전송 실패가 매매 로직을 막지 않도록 모두 try/except.
"""
import logging

import requests

from core.config import TELEGRAM_TOKEN
from core.db import get_jongalab_db

logger = logging.getLogger("TradingNotify")

_TIMEOUT = 10


def _admin_chat_ids() -> list[str]:
    with get_jongalab_db() as (conn, cursor):
        cursor.execute(
            "SELECT id FROM telegram_users WHERE is_active = TRUE AND role = 'ADMIN'"
        )
        return [str(r["id"]) for r in cursor.fetchall()]


def notify_admin(message: str) -> int:
    """ADMIN 유저에게 텔레그램 전송. 보낸 채팅 수 반환(실패 시 0, 예외 삼킴)."""
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN 없음 — 알림 생략")
        return 0
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    sent = 0
    try:
        chat_ids = _admin_chat_ids()
    except Exception as e:
        logger.error("관리자 chat id 조회 실패: %s", e)
        return 0
    for cid in chat_ids:
        try:
            resp = requests.post(
                url,
                data={
                    "chat_id": cid,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            sent += 1
        except Exception as e:
            logger.error("텔레그램 전송 실패 [%s]: %s", cid, e)
    return sent
