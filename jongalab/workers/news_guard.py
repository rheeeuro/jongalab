"""뉴스 베토 감시 — 보유 종목의 밤사이 중대 악재를 판정해 개장 즉시 전량매도를 트리거한다.

종가베팅 포지션(전일 KRX 15시대 / NXT 19시대 매수)은 다음 날 아침 settle/monitor 가
정상 흐름(NXT 08:03 반매도 → 09:28 전량청산)으로 정리한다. 이 워커는 그 전에, 밤사이
'시초가 갭하락이 거의 확실한 중대 악재'(HLB FDA 승인 실패류)가 터진 보유 종목을 찾아
news_veto_verdict(severe=1) 에 기록한다 — trading monitor(08:01~09:30 폴링)가 이를 읽어
가장 이른 거래소(NXT 가능 08시대 / 아니면 KRX 09:00 개장 직후)에서 즉시 전량 매도한다.

흐름 (NEWS_GUARD_POLL_SEC=5분 폴링, 평일 07:00~09:25 자체 종료):
  1. trading.position 보유 종목 조회(읽기 전용) — 보유 없으면 종료
  2. 종목별 news_mention 을 전거래일 15:00 이후로 조회(telegram_listener 가 상시 적재)
  3. 이미 severe 확정이거나 신규 헤드라인이 없으면 스킵(LLM 절약 — 아침당 0~10회 호출)
  4. OpenAI 판정(core/news_veto_judge, temperature=0) → news_veto_verdict upsert
     (severe 는 confidence >= NEWS_GUARD_MIN_CONFIDENCE 일 때만)
  5. severe 신규 확정 시 관리자 텔레그램 경보

실패 안전: trading DB/LLM 실패는 해당 사이클·종목만 건너뛰고 다음 폴링에 재시도한다.
판정이 없으면 trading 쪽은 미개입 — 기존 settle 흐름(09:28 데드라인)이 그대로 백스톱.
PM2 cron(평일 07:00, autorestart:false) + 진입부 거래일/시간창 가드(pm2 restart 즉시 기동 방어).
--once 는 창 가드를 무시하고 1사이클만 도는 수동 검증용.
"""
import argparse
import logging
import time as time_mod
from datetime import datetime

from core.logging_setup import setup_logging
from core.config import NEWS_GUARD_POLL_SEC, NEWS_GUARD_MAX_HEADLINES, OPENAI_MODEL
from core.market_calendar import exit_if_not_trading_day
from core.news_veto_judge import news_window_start, judge_headlines, is_actionable
from core.notifications import send_news_veto_alert
from core.repository import news as news_repo
from core.repository import news_veto as news_veto_repo
from core.repository import trading_position

setup_logging()
logger = logging.getLogger("NewsGuard")

WINDOW_START = (7, 0)
WINDOW_END = (9, 25)


def in_window(now: datetime) -> bool:
    """가동 구간: 평일 07:00~09:25. monitor(~09:30)가 매도를 소화할 시간을 남기고 먼저 끝낸다."""
    if now.weekday() >= 5:
        return False
    return WINDOW_START <= (now.hour, now.minute) <= WINDOW_END


def run_cycle(verdict_date: str, since: datetime) -> int:
    """한 사이클: 보유 종목 × 신규 뉴스 판정. 반환: LLM 판정 시도 수 (보유 없음이면 -1).

    종목 단위로 예외를 격리한다 — 한 종목의 조회/판정 실패가 나머지 감시를 막지 않는다.
    """
    try:
        positions = trading_position.get_open_positions()
    except Exception as e:
        logger.error("보유 포지션 조회 실패(다음 폴링 재시도): %s", e)
        return 0
    if not positions:
        return -1

    judged = 0
    for pos in positions:
        stk_cd = pos["stk_cd"]
        try:
            rows = news_repo.get_news_since(stk_cd, since, NEWS_GUARD_MAX_HEADLINES)
            if not rows:
                continue
            existing = news_veto_repo.get_verdict(verdict_date, stk_cd)
            if existing and existing["severe"]:
                continue  # 이미 발동 확정 — 재판정 불필요(강등 금지와 짝)
            news_max_at = max(r["created_at"] for r in rows)
            if existing and existing.get("news_max_at") and existing["news_max_at"] >= news_max_at:
                continue  # 신규 헤드라인 없음 — LLM 호출 절약
            stk_nm = rows[-1].get("company_name") or stk_cd

            judged += 1
            verdict = judge_headlines(stk_nm, stk_cd, rows)
            if verdict is None:
                continue  # LLM 실패/형식 불량 — 기록하지 않고 다음 폴링 재시도

            severe = is_actionable(verdict)
            news_veto_repo.upsert_verdict(
                verdict_date, stk_cd, stk_nm, int(severe),
                verdict["confidence"], verdict["category"], verdict["reason"],
                [r["headline"] for r in rows], news_max_at, OPENAI_MODEL,
            )
            if severe:
                logger.warning("🚨 뉴스 베토 severe 확정 [%s %s] %s(확신도 %d): %s",
                               stk_cd, stk_nm, verdict["category"], verdict["confidence"],
                               verdict["reason"])
                send_news_veto_alert(stk_nm, stk_cd, verdict["category"],
                                     verdict["confidence"], verdict["reason"],
                                     verdict["evidence"])
            else:
                logger.info("뉴스 베토 비발동 [%s %s] severe=%s 확신도=%d (%s)",
                            stk_cd, stk_nm, verdict["severe"], verdict["confidence"],
                            verdict["category"])
        except Exception as e:
            logger.error("뉴스 베토 점검 실패 [%s]: %s", stk_cd, e)
    return judged


def main() -> int:
    parser = argparse.ArgumentParser(description="뉴스 베토 감시 워커")
    parser.add_argument("--once", action="store_true",
                        help="시간창 가드를 무시하고 1사이클만 실행(수동 검증용)")
    args = parser.parse_args()

    exit_if_not_trading_day()
    now = datetime.now()
    verdict_date = now.strftime("%Y%m%d")
    since = news_window_start(now)

    if args.once:
        n = run_cycle(verdict_date, since)
        logger.info("1사이클 완료 (판정 %d건)", max(n, 0))
        return 0

    if not in_window(now):
        logger.info("가동 구간(평일 %02d:%02d~%02d:%02d) 밖 — 종료",
                    *WINDOW_START, *WINDOW_END)
        return 0

    logger.info("뉴스 베토 감시 시작 (뉴스 창 %s~, %d초 폴링, %02d:%02d 자체 종료)",
                since, NEWS_GUARD_POLL_SEC, *WINDOW_END)
    while in_window(datetime.now()):
        n = run_cycle(verdict_date, since)
        if n == -1:
            logger.info("보유 포지션 없음 — 감시할 대상이 없어 종료")
            return 0
        time_mod.sleep(NEWS_GUARD_POLL_SEC)
    logger.info("가동 구간 종료 — 뉴스 베토 감시 종료")
    return 0


if __name__ == "__main__":
    main()
