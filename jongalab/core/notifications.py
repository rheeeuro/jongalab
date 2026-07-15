"""
알림 모듈 - 텔레그램 메시지 전송 로직 통합
"""
import logging
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from core.config import TELEGRAM_BOT_TOKEN
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
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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


def send_job_alert(job_name: str, status: str, exit_code: int | None, log_tail: str = ""):
    """스케줄러 잡 실패/타임아웃 경보 — 관리자(ADMIN)에게만 (workers/scheduler.py 전용).

    경보 실패가 스케줄러를 죽이면 안 되므로 예외는 삼키고 로그만 남긴다.
    """
    try:
        detail = f"\n```\n{log_tail[-700:]}\n```" if log_tail else ""
        message = (
            f"🚨 *[스케줄러] {job_name} {status}* "
            f"{datetime.now():%Y-%m-%d %H:%M}\n"
            f"exit={exit_code} — 관리자 워커 현황 페이지·`logs/jobs/{job_name}.log` 확인{detail}"
        )
        count = _send_telegram_admin(message)
        logging.info(f"📨 스케줄러 경보 전송: {job_name} {status} -> {count}개 채팅방")
    except Exception as e:
        logging.error(f"❌ 스케줄러 경보 전송 실패: {e}")


def send_news_veto_alert(stk_nm: str, stk_cd: str, category: str, confidence: int,
                         reason: str, evidence: list[str] | None = None):
    """뉴스 베토 severe 판정 경보 — 관리자 전용 (workers/news_guard.py).

    경보 실패가 판정 루프를 막으면 안 되므로 예외는 삼키고 로그만 남긴다.
    """
    try:
        ev = "\n".join(f"  · {e}" for e in (evidence or [])[:2])
        message = (
            f"🚨 *뉴스 베토 판정* {stk_nm}(`{stk_cd}`)\n"
            f"분류: {category} · 확신도 {confidence}\n"
            f"사유: {reason}\n"
            + (f"근거:\n{ev}\n" if ev else "")
            + "→ 개장 즉시 전량 매도 예정 (NXT 가능 시 08시대, 아니면 09:00 KRX)"
        )
        count = _send_telegram_admin(message)
        logging.info(f"📨 뉴스 베토 경보 전송: {stk_cd} -> {count}개 채팅방")
    except Exception as e:
        logging.error(f"❌ 뉴스 베토 경보 전송 실패: {e}")


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


def build_gap_check_message(
    report_date: str, check_time: str, rows: list[dict]
) -> tuple[str, int, int]:
    """갭 체크 최종 메시지 본문 생성. 반환: (message, wins, losses)

    rows: [{rank, name, score, venue, base_price, now_price, pct, approx?, error?}]
      venue "NXT": 전일 19:50 NXT → 당일 08:03 NXT
      venue "KRX": 전일 15:20 KRX → 당일 09:03 KRX
      approx=True 는 기준가 미수집 폴백(리포트 시점 가격 대비) — pct 뒤 ≈ 표시.
    """
    ups, downs, flats, errors = [], [], [], []
    for r in rows:
        pct = r.get("pct")
        if r.get("error") or pct is None:
            errors.append(r)
        elif pct > 0:
            ups.append(r)
        elif pct < 0:
            downs.append(r)
        else:
            flats.append(r)

    def _fmt(r: dict, emoji: str) -> str:
        mark = "≈" if r.get("approx") else ""
        return (
            f"{emoji} `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`\n"
            f"    `[{r['venue']}]` `{r['pct']:+.2f}%{mark}`  "
            f"({r['base_price']:,} → {r['now_price']:,})"
        )

    def _fmt_simple(r: dict) -> str:
        return f"   `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`"

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
    if errors:
        sections.append(
            f"❓ *조회실패 ({len(errors)})*\n"
            + "\n".join(_fmt_simple(r) for r in sorted(errors, key=by_rank))
        )

    wins, losses = len(ups), len(downs)
    total_tracked = wins + losses + len(flats)
    win_rate = (wins / total_tracked * 100) if total_tracked else 0.0

    footnotes = ["_NXT: 전일 19:50→08:03 · KRX: 전일 15:20→09:03_"]
    if any(r.get("approx") for r in rows):
        footnotes.append("_≈ 기준가 미수집 → 리포트 시점 가격 대비_")

    message = (
        f"📊 *[갭 체크] {report_date} Top 10*\n"
        f"({check_time} 확정)\n\n"
        f"🏆 *{wins}승 {losses}패* "
        f"(보합 {len(flats)} / 승률 {win_rate:.0f}%)\n"
        f"──────────────────\n\n"
        + "\n\n".join(sections)
        + "\n\n"
        + "\n".join(footnotes)
    )
    return message, wins, losses


def send_edge_rule_alert(
    promotions: list[dict], demotions: list[dict], exec_pending: list[dict] | None = None
):
    """Edge Ledger 상태 전이 알림 — 관리자(ADMIN)에게만. 실제 전이는 수동 승인이며 이건 알림뿐.

    promotions:   승격 후보 — core.edge_policy.check_promotion 게이트 전체 충족 candidate.
    exec_pending: 집행 설계 필요 — 통계 게이트는 충족했지만 선정 시점(13~15시) 실행 불가
                  피처를 써서 승격이 막힌 candidate(페이퍼 엣지 확인, 집행 시점 재설계 후보).
    demotions:    강등 검토(최근 표본 mean_net<0) live rule 요약.
    각 항목: {name, family, n, mean_net, ci_low[, reason]}. 전부 비면 전송하지 않는다.
    """
    exec_pending = exec_pending or []
    if not promotions and not demotions and not exec_pending:
        return

    def _pct(v) -> str:
        return f"{v:+.2f}%" if v is not None else "—"  # 표본 0 등 미산출 값 방어

    def _rule_line(r: dict, prefix: str = "평균순수익") -> str:
        line = f"• *{r['name']}* (`{r['family']}`) — n={r['n']}, {prefix} {_pct(r.get('mean_net'))}"
        if "ci_low" in r:
            line += f", CI하한 {_pct(r.get('ci_low'))}"
        return line

    try:
        sections = []
        if promotions:
            sections.append(
                "🟢 *승격 후보 (candidate→live 검토)*\n"
                + "\n".join(_rule_line(r) for r in promotions)
            )
        if exec_pending:
            sections.append(
                "🟡 *집행 설계 필요 (통계 충족, 선정 시점 실행 불가 피처)*\n"
                + "\n".join(_rule_line(r) for r in exec_pending)
            )
        if demotions:
            sections.append(
                "🔴 *강등 검토 (live→retired 판단)*\n"
                + "\n".join(_rule_line(r, prefix="최근 평균순수익") for r in demotions)
            )
        message = (
            "🧪 *[Edge Ledger] 상태 전이 알림*\n"
            "_전이는 관리자 API 수동 승인 — 아래는 후보일 뿐입니다._\n"
            "──────────────────\n\n"
            + "\n\n".join(sections)
        )
        count = _send_telegram_admin(message)
        logging.info(
            f"📨 Edge Ledger 알림 전송 -> {count}개 (승격후보 {len(promotions)} / "
            f"집행설계필요 {len(exec_pending)} / 강등검토 {len(demotions)})"
        )
    except Exception as e:
        logging.error(f"❌ Edge Ledger 알림 실패: {e}")


def send_gap_check_alert(report_date: str, check_time: str, rows: list[dict]):
    """갭 체크 최종 리포트 전송 — KRX 체크(09:03)까지 끝난 뒤 하루 한 번만 호출된다.

    rows 형식은 build_gap_check_message() docstring 참고.
    """
    try:
        message, wins, losses = build_gap_check_message(report_date, check_time, rows)
        count = _send_telegram_message(message)
        logging.info(
            f"📨 갭 체크 전송 완료 -> {count}개 채팅방 "
            f"({wins}승 {losses}패)"
        )

    except Exception as e:
        logging.error(f"❌ 갭 체크 전송 실패: {e}")
