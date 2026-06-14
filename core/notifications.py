"""
알림 모듈 - 텔레그램 메시지 전송 로직 통합
"""
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from core.config import TELEGRAM_TOKEN
from core.repository import get_active_chat_ids


_retry = Retry(
    total=5,
    connect=5,
    read=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"],
    raise_on_status=False,
)
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=_retry))


def _post(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    resp = _session.post(url, data=data, timeout=10)
    resp.raise_for_status()


def _send_telegram_message(message: str):
    """활성 상태인 모든 유저에게 전송"""
    chat_ids = get_active_chat_ids()
    for chat_id in chat_ids:
        _post(chat_id, message)
    return len(chat_ids)


def _send_telegram_admin(message: str):
    """ADMIN 역할 유저에게만 전송"""
    chat_ids = get_active_chat_ids(role="ADMIN")
    for chat_id in chat_ids:
        _post(chat_id, message)
    return len(chat_ids)


def send_analysis_alert(channel: str, title: str, analysis: str, score: int = 50, related_tickers: list[dict] | None = None):
    """콘텐츠 분석 결과 텔레그램 전송 (YouTube/Telegram 공통)"""
    try:
        if score >= 80:
            status = "🔥 *강력 매수* (탐욕)"
        elif score >= 60:
            status = "📈 *긍정적* (매수)"
        elif score <= 20:
            status = "🥶 *공포* (현금화)"
        elif score <= 40:
            status = "📉 *부정적* (보수적)"
        else:
            status = "😐 *중립* (관망)"

        short_analysis = analysis[:800] + "..." if len(analysis) > 800 else analysis

        ticker_display = ", ".join(
            f"{t['name']}({t['ticker']})" for t in (related_tickers or [])
        )

        formatted_analysis = short_analysis.replace("**", "*")
        message = (
            f"🚨 *[{channel}] 분석 완료!*\n"
            f"📊 관점: {score}점 - {status}\n\n"
            f"📺 {title}\n"
            f"관련 종목: {ticker_display}\n"
            f"──────────────────\n"
            f"{formatted_analysis}\n\n"
            f"👉 [대시보드 바로가기](https://jongalab.com)"
        )

        count = _send_telegram_message(message)
        logging.info(f"📨 텔레그램 전송 성공: {title} ({score}점) -> {count}개 채팅방")

    except Exception as e:
        logging.error(f"❌ 텔레그램 에러: {e}")


def send_daily_digest_alert(date: str, buy: str, buy_reason: str, sell: str, sell_reason: str):
    """일일 요약 리포트 텔레그램 전송"""
    try:
        message = (
            f"📅 *[{date}] 오늘의 AI 투자 전략*\n\n"
            f"🐂 *매수(Buy): {buy}*\n"
            f"└ {buy_reason}\n\n"
            f"🐻 *매도(Sell): {sell}*\n"
            f"└ {sell_reason}\n\n"
            f"👉 [대시보드 확인하기](https://jongalab.com)"
        )

        count = _send_telegram_message(message)
        logging.info(f"📨 텔레그램 전송 완료 -> {count}개 채팅방")

    except Exception as e:
        logging.error(f"❌ 텔레그램 전송 실패: {e}")


def send_gap_check_alert(
    report_date: str, check_time: str, rows: list[dict], is_retry: bool = False
):
    """갭상승 체크 리포트 — ADMIN 유저에게만 전송

    초기(8:10) rows: [{rank, name, report_price, now_price, pct, error?, pending?}]
    재조회(9:10) rows: [{rank, name, report_price,
        nxt_price?, nxt_pct?, krx_price?, krx_pct?, krx_from_nxt_pct?, error?}]
        — 분류는 krx_pct(우선) / nxt_pct(폴백) 기준.
    """
    try:
        ups, downs, flats, pendings, errors = [], [], [], [], []
        for r in rows:
            if r.get("error"):
                errors.append(r)
                continue
            if r.get("pending"):
                pendings.append(r)
                continue
            if is_retry:
                pct = r.get("krx_pct", r.get("nxt_pct"))
            else:
                pct = r.get("pct")
            if pct is None:
                errors.append(r)
                continue
            if pct > 0:
                ups.append(r)
            elif pct < 0:
                downs.append(r)
            else:
                flats.append(r)

        def _fmt_initial(r: dict, emoji: str) -> str:
            return (
                f"{emoji} `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`\n"
                f"    `{r['pct']:+.2f}%`  "
                f"({r['report_price']:,} → {r['now_price']:,})"
            )

        def _fmt_retry(r: dict, emoji: str) -> str:
            lines = [f"{emoji} `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`"]
            if "nxt_pct" in r:
                lines.append(
                    f"    `[NXT]` `{r['nxt_pct']:+.2f}%`  "
                    f"({r['report_price']:,} → {r['nxt_price']:,})"
                )
            if "krx_pct" in r:
                if "krx_from_nxt_pct" in r:
                    lines.append(
                        f"    `[KRX]` `{r['krx_from_nxt_pct']:+.2f}%`  "
                        f"({r['nxt_price']:,} → {r['krx_price']:,})"
                    )
                else:
                    lines.append(
                        f"    `[KRX]` `{r['krx_pct']:+.2f}%`  "
                        f"({r['report_price']:,} → {r['krx_price']:,})"
                    )
            return "\n".join(lines)

        def _fmt_simple(r: dict) -> str:
            return f"   `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`"

        _fmt = _fmt_retry if is_retry else _fmt_initial
        by_rank = lambda x: x["rank"]
        sections = []
        if ups:
            sections.append(
                f"🔴 *갭상승 ({len(ups)})*\n"
                + "\n".join(_fmt(r, "•") for r in sorted(ups, key=by_rank))
            )
        if downs:
            sections.append(
                f"🔵 *갭하락 ({len(downs)})*\n"
                + "\n".join(_fmt(r, "•") for r in sorted(downs, key=by_rank))
            )
        if flats:
            sections.append(
                f"⚪ *보합 ({len(flats)})*\n"
                + "\n".join(_fmt(r, "•") for r in sorted(flats, key=by_rank))
            )
        if pendings:
            sections.append(
                f"⏳ *장 시작 대기 ({len(pendings)})*\n"
                + "\n".join(_fmt_simple(r) for r in sorted(pendings, key=by_rank))
            )
        if errors:
            sections.append(
                f"❓ *조회실패 ({len(errors)})*\n"
                + "\n".join(_fmt_simple(r) for r in sorted(errors, key=by_rank))
            )

        wins, losses = len(ups), len(downs)
        total_tracked = wins + losses + len(flats)
        win_rate = (wins / total_tracked * 100) if total_tracked else 0.0

        if is_retry:
            message = (
                f"🔄 *[갭 체크 최종] {report_date}*\n"
                f"(장 시작 후 재조회 → {check_time})\n\n"
                f"🏆 *{wins}승 {losses}패* "
                f"(보합 {len(flats)} / 승률 {win_rate:.0f}%)\n"
                f"──────────────────\n\n"
                + "\n\n".join(sections)
            )
        else:
            message = (
                f"📊 *[갭 체크] {report_date} Top 10*\n"
                f"(리포트 시각 → {check_time})\n\n"
                f"🏆 *{wins}승 {losses}패* "
                f"(보합 {len(flats)} / 승률 {win_rate:.0f}%)\n"
                f"──────────────────\n\n"
                + "\n\n".join(sections)
            )

        count = _send_telegram_admin(message)
        logging.info(
            f"📨 갭 체크 전송 완료 -> {count}개 채팅방 "
            f"({wins}승 {losses}패)"
        )

    except Exception as e:
        logging.error(f"❌ 갭 체크 전송 실패: {e}")
