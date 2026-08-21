"""
알림 모듈 - 텔레그램 메시지 전송 로직 통합
"""
import html
import logging
import re
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


def _post(chat_id: str, message: str, parse_mode: str = "Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    resp = _session.post(url, data=data, timeout=10)
    resp.raise_for_status()


def _send_telegram_message(message: str, parse_mode: str = "Markdown"):
    """활성 상태인 모든 유저에게 전송"""
    chat_ids = get_active_chat_ids()
    for chat_id in chat_ids:
        _post(chat_id, message, parse_mode)
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


TELEGRAM_MAX_LEN = 4096   # sendMessage text 상한. 초과하면 400 이라 알림이 통째로 누락된다
ORIGINAL_MAX_LEN = 2500   # 원문 인용 상한. 텔레그램 4096자 제한 안에서 헤더·요약 자리를 남긴다
BODY_MAX_LEN = 800        # 덧붙이는 코멘트 상한(원문 없는 YouTube 경로의 분석 본문)


def _esc(text: str) -> str:
    """HTML parse_mode 용 이스케이프. 원문에 `*`·`_`·`[` 가 있어도 안전하다.

    Markdown 이던 시절엔 LLM/원문의 짝 안 맞는 `*`·`_` 하나가 400 을 만들어 알림이
    조용히 누락됐다(예외를 삼키고 로그만 남기는 구조라 눈에 띄지 않았다).
    """
    return html.escape(str(text or ""), quote=False)


def _md_bold_to_html(text: str) -> str:
    """이스케이프된 텍스트의 `**강조**` 만 <b> 로 바꾼다(짝이 맞는 쌍만 — 잘린 `**` 는 그대로 남겨
    태그 미종료로 400 이 나는 걸 막는다)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def send_journal_post(text: str) -> int:
    """변경사항 저널(workers/journal.py) 게시글 초안 — 관리자에게 평문으로 전송.

    게시글에 그대로 복사해 쓰는 글이라 parse_mode 없이 보낸다(마크다운 기호가 400 을 만들거나
    본문에서 사라지지 않게). 4096자 상한을 넘으면 줄 경계로 나눠 여러 통으로 보낸다.
    전송 실패가 파일 생성을 무르게 하면 안 되므로 예외는 삼키고 로그만 남긴다.
    """
    sent = 0
    try:
        chat_ids = get_active_chat_ids(role="ADMIN")
        chunks, buf = [], ""
        for line in text.splitlines(keepends=True):
            if len(buf) + len(line) > TELEGRAM_MAX_LEN - 96:
                chunks.append(buf)
                buf = ""
            buf += line[:TELEGRAM_MAX_LEN - 96]
        if buf.strip():
            chunks.append(buf)
        for chat_id in chat_ids:
            for i, chunk in enumerate(chunks):
                head = f"📝 ({i + 1}/{len(chunks)})\n" if len(chunks) > 1 else ""
                _post(chat_id, head + chunk.strip(), parse_mode=None)
                sent += 1
        logging.info(f"📨 저널 전송: {len(chat_ids)}개 채팅방 x {len(chunks)}통")
    except Exception as e:
        logging.error(f"❌ 저널 전송 실패: {e}")
    return sent


def send_analysis_alert(
    channel: str,
    title: str,
    analysis: str,
    score: int = 50,
    related_tickers: list[dict] | None = None,
    original_text: str | None = None,
    tldr: str | None = None,
    source_url: str | None = None,
):
    """콘텐츠 분석 결과 텔레그램 전송 (YouTube/Telegram 공통).

    `original_text` 가 오면(텔레그램 채널 경로) **원문을 접히는 인용블록으로 그대로 싣고**
    코멘트를 덧붙인다 — 봇은 자기가 멤버가 아닌 채널의 메시지를 forwardMessage 할 수 없어
    (원문 수집은 Telethon 사용자 세션, 발송은 봇) 네이티브 '전달'은 불가능하고, 인용블록이
    같은 읽기 경험을 준다. 원문이 있으면 코멘트는 `tldr` 한 줄만 붙인다(원문이 이미 실려
    있어 분석 전문까지 넣으면 모바일에서 스크롤만 길어진다). 없으면 기존대로 분석 본문.

    parse_mode 는 이 함수만 HTML 이다(원문의 임의 문자 때문 — 다른 알림은 Markdown 유지).
    """
    try:
        if score >= 80:
            status = "🔥 <b>강력 매수</b> (탐욕)"
        elif score >= 60:
            status = "📈 <b>긍정적</b> (매수)"
        elif score <= 20:
            status = "🥶 <b>공포</b> (현금화)"
        elif score <= 40:
            status = "📉 <b>부정적</b> (보수적)"
        else:
            status = "😐 <b>중립</b> (관망)"

        ticker_display = ", ".join(
            f"{_esc(t['name'])}(<code>{_esc(t['ticker'])}</code>)"
            for t in (related_tickers or [])
        )

        head = f"📨 <b>{_esc(channel)}</b>" if original_text else f"🚨 <b>[{_esc(channel)}] 분석 완료!</b>"
        lines = [head, f"📊 관점: {score}점 - {status}", ""]
        if not original_text:
            lines.append(f"📺 {_esc(title)}")
        if ticker_display:
            lines.append(f"관련 종목: {ticker_display}")

        footer = ['👉 <a href="https://jongalab.com">대시보드 바로가기</a>']
        if source_url:
            footer.append(f'<a href="{_esc(source_url)}">원문 보기</a>')
        tail = "\n" + " · ".join(footer)

        if original_text:
            body = f"\n🤖 {_md_bold_to_html(_esc(_clip(tldr or analysis, BODY_MAX_LEN)))}"
            quoted = _esc(_clip(original_text, ORIGINAL_MAX_LEN))
            # 이스케이프(&→&amp;)로 부푼 드문 원문에서 4096자를 넘기지 않게 인용분만 더 깎는다
            budget = TELEGRAM_MAX_LEN - len("\n".join(lines)) - len(body) - len(tail) - 40
            if len(quoted) > budget:
                # 자를 때 `&amp;` 중간에서 끊기면 엔티티가 깨지므로 꼬리 조각을 떼어낸다
                quoted = re.sub(r"&[#a-zA-Z0-9]{0,6}$", "", quoted[: max(200, budget)]) + "…"
            # expandable: 4줄 넘으면 텔레그램이 접어서 보여준다(긴 리서치 원문 대응)
            lines.append(f"\n<blockquote expandable>{quoted}</blockquote>")
            lines.append(body)
        else:
            lines.append("──────────────────")
            lines.append(_md_bold_to_html(_esc(_clip(analysis, BODY_MAX_LEN))))

        lines.append(tail)
        count = _send_telegram_message("\n".join(lines), parse_mode="HTML")
        logging.info(f"📨 텔레그램 전송 성공: {title} ({score}점) -> {count}개 채팅방")

    except Exception as e:
        logging.error(f"❌ 텔레그램 에러: {e}")


def build_gap_check_message(
    report_date: str, check_time: str, rows: list[dict]
) -> tuple[str, int, int]:
    """갭 체크 최종 메시지 본문 생성. 반환: (message, wins, losses)

    rows: [{rank, name, score, venue, base_price, now_price, pct, approx?, ex_rights_ratio?, error?}]
      venue "NXT": 전일 19:50 NXT → 당일 08:03 NXT
      venue "KRX": 전일 15:20 KRX → 당일 09:03 KRX
      approx=True 는 기준가 미수집 폴백(리포트 시점 가격 대비) — pct 뒤 ≈ 표시.
      ex_rights_ratio 는 무상증자 권리락 조정 기준가로 측정한 행 — pct 뒤 † 표시(sql/50).
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
        mark = ("≈" if r.get("approx") else "") + ("†" if r.get("ex_rights_ratio") else "")
        return (
            f"{emoji} `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`\n"
            f"    `[{r['venue']}]` `{r['pct']:+.2f}%{mark}`  "
            f"({r['base_price']:,} → {r['now_price']:,})"
        )

    def _fmt_simple(r: dict) -> str:
        return f"   `{r['rank']:>2}`. *{r['name']}* `{r['score']}점`"

    # 화면 목록과 같은 순서 — 규칙 수 내림차순 → rank_no 오름차순.
    # (`rules` 가 없는 옛 payload 는 0 으로 떨어져 기존 rank 순이 된다)
    by_rank = lambda x: (-x.get("rules", 0), x["rank"])
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
    if any(r.get("ex_rights_ratio") for r in rows):
        footnotes.append("_† 무상증자 권리락 조정 기준가 대비(배정비율 반영)_")

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
    promotions: list[dict], transitions: list[dict], exec_pending: list[dict] | None = None,
    promoted: list[dict] | None = None, retirements: list[dict] | None = None,
):
    """Edge Ledger 알림 — 관리자(ADMIN)에게만. **줄마다 성격이 다르니 섹션을 섞지 않는다.**

    promoted:     자동 승격(원장 축) — 판정일 게이트와 누적 게이트를 둘 다 통과해 평가기가
                  **이미 candidate → live 로 올린** 건이다. 승인 요청이 아니라 사후 보고다.
                  판정일에 1회만 온다(sql/39). 어느 판정일인지는 `stage` 가 알려준다:
                  `confirm` 은 발견 구간과 겹치지 않는 새 표본에서 평균수익이 재현됐다는 뜻이고,
                  `discovery` 는 확인창이 면제되는 experimental 정책에서 발견 판정만으로 승격
                  가능해진 건이다.
    promotions:   승격 **승인 대기** — 판정일 게이트는 통과했지만 누적 게이트가 미달이라 자동
                  승격이 보류된 candidate. 종결이 아니고, 라우터로 수동 승격할 수 있다.
                  무엇이 막고 있는지는 `reason` 에 실린다.
    exec_pending: 집행 설계 필요 — 통계는 확증됐지만 선정 시점(13~15시) 실행 불가 피처를 써서
                  승격이 막힌 candidate(집행 시점 재설계 후보). 통계 탈락이 아니므로 종결이 아니다.
    retirements:  자동 종결(원장 축) — 판정(발견창/확인창)에서 탈락해 **이미 retired 로 내려간**
                  건이다. 사후 보고이며, 재도전 경로는 `unretire`(표본 리셋) 하나뿐이라
                  줄에 그 안내를 함께 싣는다. 판정 탈락이 아닌 종결(성적 붕괴·실행 불가 등)은
                  여전히 관리자만 결정한다.
    transitions:  운용 전이(운용 축) — live ↔ paused 가 **이미 자동으로 바뀐** 사후 보고다.
                  승인 요청이 아니다. 판정 자는 **시장 조정 alpha**(절대 수익은 시장과
                  동기화되고, 초과수익은 beta=1 을 강제해 저beta 방어형 룰을 죽인다 —
                  core.edge_policy.decide_transition). **역할별 부호가 반대**다(selector 는 매수
                  종목 alpha<0, veto 는 제외 종목 alpha>0). 되돌릴 수 있는 전이라 자동이며,
                  영구 종결(retired)은 여전히 사람만 결정한다.
    각 항목: {name, family, n, mean_net, ci_low[, stage, mean_net_days, confirm_mean_net,
    mean_exc, reason, alpha, beta, down_day_mean, down_day_n, from, to]}.
    전부 비면 전송하지 않는다.
    """
    exec_pending = exec_pending or []
    promoted = promoted or []
    retirements = retirements or []
    if not (promoted or promotions or transitions or exec_pending or retirements):
        return

    def _pct(v) -> str:
        return f"{v:+.2f}%" if v is not None else "—"  # 표본 0 등 미산출 값 방어

    _PROMO_STAGE_TEXT = {
        "confirm": "확인창 확증",
        "discovery": "발견 통과 · 실험 적용(확인창 면제)",
    }

    def _rule_line(r: dict, prefix: str = "평균순수익") -> str:
        # veto 는 mean_net 이 **제외한** 종목의 성적이라 음수가 정상(승격 조건과 같은 방향).
        # 부호 방향을 줄에 못 박아 두지 않으면 잘 작동하는 veto 를 나쁜 성적으로 읽는다.
        if r.get("role") == "veto":
            prefix = f"제외 종목 {prefix}(음수=정상)"
        line = f"• *{r['name']}* (`{r['family']}`) — n={r['n']}, {prefix} {_pct(r.get('mean_net'))}"
        if "ci_low" in r:
            line += f", CI하한 {_pct(r.get('ci_low'))}"
        # 확인창 평균수익 — 승격 후보의 핵심 근거(발견에 쓰지 않은 새 표본에서의 성적).
        # 2026-08-04: 판정 자가 초과수익 → 절대 평균수익으로 바뀌어 이 줄도 같은 자로 찍는다.
        if r.get("confirm_mean_net") is not None:
            line += f", 확인창 평균수익 {_pct(r.get('confirm_mean_net'))}"
        # 초과수익은 게이트에 쓰지 않지만 "장 덕에 올랐나"의 참고값이라 함께 보여준다.
        if r.get("mean_exc") is not None:
            line += f", 참고 초과 {_pct(r.get('mean_exc'))}"
        # 일 등가중 최근 평균(강등 검토 전용) — 게이트는 종목-일 가중을 보지만, 두 가중의
        # **부호가 갈리면 몇 종목의 급등이 평균을 만든 쏠림**이라 강등 근거가 되지 못한다.
        # 게이트 조건은 2026-07-28 결정(효과 크기는 종목-일)대로 두고 판단 재료만 노출한다.
        # 실례: veto_bio_kosdaq 2026-07-29 알림 +0.18%(종목-일) vs -0.20%(일 등가중) — 상위
        # 3건(HLB +10.7·펩트론 +7.8·디앤디파마텍 +3.9)을 빼면 -0.70%, 대체효과는 veto 이득 방향.
        # 어느 판정일에 온 알림인지 — 확인창 확증과 발견 통과는 근거의 무게가 다르다.
        stage = _PROMO_STAGE_TEXT.get(r.get("stage") or "")
        if stage:
            line += f" [{stage}]"
        mnd = r.get("mean_net_days")
        if mnd is not None:
            line += f", 일등가중 {_pct(mnd)}"
            mn = r.get("mean_net")
            if mn is not None and (mn > 0) != (mnd > 0):
                line += " ⚠️쏠림(부호 상충 — 대체효과·꼬리 재계산 필요)"
        # 강등 게이트가 실제로 본 값 — 절대 수익이 아니라 **시장 조정 alpha** 다.
        # beta 와 하락일 성적을 함께 찍어 "장이 나빠서인가 룰이 죽었나"를 줄에서 가른다.
        if r.get("alpha") is not None:
            line += f"\n  ↳ 판정값 alpha {_pct(r.get('alpha'))}"
            if r.get("beta") is not None:
                line += f" (beta {r['beta']:+.2f})"
            if r.get("down_day_mean") is not None:
                line += f", 하락일 {_pct(r.get('down_day_mean'))}(n={r.get('down_day_n')})"
        # 전이 사유 — **연속 확인이 됐다는 사실**이 여기 실린다(하루짜리 신호가 아니라는 근거).
        # 집행 설계 필요 줄에서는 무엇이 막고 있는지가 실린다. 없으면 생략.
        if r.get("reason"):
            line += f"\n  ↳ 사유: {r['reason']}"
        return line

    try:
        sections = []
        if promoted:
            sections.append(
                "✅ *자동 승격 (candidate→live · 이미 반영됨)* — 판정 근거는 각 줄의 [ ] 표기\n"
                + "\n".join(_rule_line(r) for r in promoted)
            )
        if promotions:
            sections.append(
                "🟢 *승격 승인 대기 (판정일 통과, 누적 게이트 미달)*\n"
                + "\n".join(_rule_line(r) for r in promotions)
            )
        if exec_pending:
            sections.append(
                "🟡 *집행 설계 필요 (통계 충족, 선정 시점 실행 불가 피처)*\n"
                + "\n".join(_rule_line(r) for r in exec_pending)
            )
        # 운용 전이는 **이미 반영된** 결과라 방향별로 갈라 찍는다 — 내려간 줄과 올라온 줄이
        # 섞이면 "뭘 승인해야 하나"로 읽힌다(승인할 것이 없다).
        paused = [r for r in transitions if r.get("to") == "paused"]
        resumed = [r for r in transitions if r.get("to") == "live"]
        if paused:
            sections.append(
                "⏸️ *자동 일시중지 (live→paused · 이미 반영됨)*\n"
                + "\n".join(_rule_line(r, prefix="최근 평균순수익") for r in paused)
            )
        if resumed:
            sections.append(
                "▶️ *자동 복귀 (paused→live · 이미 반영됨)*\n"
                + "\n".join(_rule_line(r, prefix="최근 평균순수익") for r in resumed)
            )
        if retirements:
            sections.append(
                "🔴 *자동 종결 (판정 탈락 → retired · 이미 반영됨)*\n"
                + "\n".join(_rule_line(r, prefix="판정 평균순수익") for r in retirements)
            )
        # 안내는 실린 섹션에만 붙인다 — 승격만 온 날 전이 안내가 함께 붙으면 반대로 읽힌다.
        notes = []
        if promoted:
            notes.append("_자동 승격은 **이미 반영된 결과 보고**입니다(승인 불필요 — "
                         "성적이 꺾이면 자동 일시중지로 빠집니다)._")
        if promotions:
            notes.append("_승격 승인 대기는 관리자 승인이 필요합니다 — 누적 게이트가 막고 있습니다._")
        if promoted or promotions or exec_pending:
            notes.append("_승격/집행설계는 판정일 1회만 옵니다(매일 재평가 폐지, sql/39)._")
        if transitions:
            notes.append("_일시중지·복귀는 **자동 반영된 결과 보고**입니다(승인 불필요, 되돌릴 수 있음)._")
        if retirements:
            notes.append("_판정 탈락은 **자동 종결**됩니다 — 되살리려면 '재검증'(표본 리셋)뿐이고, "
                         "오늘부터의 새 표본으로 처음부터 판정합니다._")
        if promoted or transitions or retirements:
            notes.append("_판정 탈락 **외의** 종결(성적 붕괴·실행 불가 등)은 관리자만 결정합니다._")
        message = (
            "🧪 *[Edge Ledger] 상태 전이 알림*\n"
            + "\n".join(notes) + "\n"
            "──────────────────\n\n"
            + "\n\n".join(sections)
        )
        count = _send_telegram_admin(message)
        logging.info(
            f"📨 Edge Ledger 알림 전송 -> {count}개 (자동승격 {len(promoted)} / "
            f"승격승인대기 {len(promotions)} / 집행설계필요 {len(exec_pending)} / "
            f"운용전이 {len(transitions)} / 자동종결 {len(retirements)})"
        )
    except Exception as e:
        logging.error(f"❌ Edge Ledger 알림 실패: {e}")


def send_report_save_alert(error: str, candidate_count: int):
    """종가베팅 리포트 DB 저장 실패 경보 — 관리자 전용 (workers/closing_bet.py).

    저장 실패는 워커가 예외를 삼키고 로그만 남기므로(핸드오프·후속 단계는 계속 진행) 로그를
    직접 보지 않으면 하루가 지나도 모른다. 그 사이 daily_stock_report 가 비어 대시보드·갭체크·
    rule_evaluator 표본이 통째로 빠진다. 30분마다 재실행되므로 고쳐지지 않으면 반복 발송된다
    (같은 날 계속 실패한다는 사실 자체가 경보의 내용이다).

    경보 실패가 워커를 죽이면 안 되므로 예외는 삼키고 로그만 남긴다.
    """
    try:
        message = (
            f"🚨 *[종가베팅] 리포트 DB 저장 실패* {datetime.now():%Y-%m-%d %H:%M}\n"
            f"후보 {candidate_count}건이 `daily_stock_report` 에 저장되지 않았습니다.\n"
            f"```\n{error[:500]}\n```\n"
            "→ 고치기 전까지 오늘 리포트·갭체크·엣지 표본이 비어 있습니다."
        )
        count = _send_telegram_admin(message)
        logging.info(f"📨 리포트 저장 실패 경보 전송 -> {count}개 채팅방")
    except Exception as e:
        logging.error(f"❌ 리포트 저장 실패 경보 전송 실패: {e}")


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
