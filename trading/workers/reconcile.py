"""포지션 정합성 + 일일 실현손익 워커.

PM2 cron 으로 장 마감 후 실행:
  1) 키움 계좌 잔고(kt00018) ↔ 로컬 position 대조 → drift 감지·로깅
  2) 일자별 실현손익(ka10074)을 조회해 참고 로깅
로컬 상태와 실계좌가 어긋나면 가장 위험하므로 매일 확인한다.
"""
import sys
import logging
from datetime import datetime

from core.logging_setup import setup_logging
from core.kiwoom_order_client import KiwoomOrderClient, TokenUnavailable
from core.kiwoom_data_client import to_int
from core.repository import position as position_repo
from core.repository import blocklist as blocklist_repo
from core.repository import audit_log
from core.notifications import notify_admin

setup_logging()
logger = logging.getLogger("Reconcile")


def _alert_admin(summary: str) -> None:
    """reconcile 오류를 관리자 텔레그램으로 전송. notify_admin 이 예외를 삼키므로 안전."""
    notify_admin(f"🚨 *reconcile 오류* {datetime.now():%Y-%m-%d %H:%M}\n{summary}")


def main() -> int:
    now = datetime.now()
    # 실행 윈도우 가드: 평일 20시에만 동작(pm2 재시작 시 즉시 오실행 방지).
    if now.weekday() >= 5 or now.hour != 20:
        logger.info("실행 윈도우(평일 20시)가 아님 — 스킵 (%s)", now.strftime("%a %H:%M"))
        return 0

    trade_date = now.strftime("%Y%m%d")
    logger.info("포지션 정합성 점검 시작 (거래일 %s)", trade_date)
    client = KiwoomOrderClient()

    # 1) 잔고 조회 (kt00018)
    try:
        balance = client.get_balance()
    except TokenUnavailable as e:
        logger.error("토큰 없음 — 정합성 점검 불가: %s", e)
        _alert_admin(f"토큰 없음 — 정합성 점검 불가: `{e}`")
        return 1
    except Exception as e:
        logger.error("잔고 조회 실패: %s", e)
        _alert_admin(f"잔고 조회(kt00018) 실패: `{e}`")
        return 1

    # 키움 보유: stk_cd 는 접두어 1자리(A 등) + 6자리 → 접두어 제거
    broker = {}
    for h in balance.get("acnt_evlt_remn_indv_tot", []) or []:
        code = (h.get("stk_cd") or "").lstrip("AJQ")[-6:]
        if code:
            broker[code] = to_int(h.get("rmnd_qty"))

    local = {p["stk_cd"]: p["qty"] for p in position_repo.get_open_positions()}

    # 자동매매 이전 수동 보유분(blocklist)은 봇 관리 대상이 아니므로 drift 에서 제외한다.
    blocked = blocklist_repo.get_codes()
    drift, ignored = [], []
    for code in set(broker) | set(local):
        b, l = broker.get(code, 0), local.get(code, 0)
        if b != l:
            (ignored if code in blocked else drift).append(
                {"stk_cd": code, "broker": b, "local": l})

    if ignored:
        logger.info("blocklist 보유분 drift 무시 %d종목: %s", len(ignored), ignored)

    if drift:
        logger.warning("정합성 불일치 %d종목: %s", len(drift), drift)
        audit_log.append("reconcile_drift", None, {"trade_date": trade_date, "drift": drift})
        lines = "\n".join(
            f"• `{d['stk_cd']}` 키움 {d['broker']} / 로컬 {d['local']}" for d in drift
        )
        notify_admin(
            f"⚠️ *reconcile 정합성 불일치* {datetime.now():%Y-%m-%d %H:%M}\n"
            f"{len(drift)}종목 (키움↔로컬 보유수량 불일치)\n"
            f"──────────────────\n{lines}"
        )
    else:
        logger.info("정합성 OK — 로컬 %d종목, 키움 %d종목 일치", len(local), len(broker))

    # 2) 일일 실현손익 (ka10074) 참고 로깅
    try:
        pnl = client.get_daily_realized_pnl(trade_date, trade_date)
        logger.info(
            "일일 실현손익: rlzt_pl=%s, 매수=%s, 매도=%s",
            pnl.get("rlzt_pl"), pnl.get("tot_buy_amt"), pnl.get("tot_sell_amt"),
        )
    except Exception as e:
        logger.warning("실현손익(ka10074) 조회 실패: %s", e)
        _alert_admin(f"실현손익(ka10074) 조회 실패: `{e}`")

    logger.info("포지션 정합성 점검 종료")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        logger.exception("reconcile 비정상 종료")
        _alert_admin(f"비정상 종료(예외): `{e}`")
        rc = 1
    sys.exit(rc)
