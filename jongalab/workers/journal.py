"""변경사항 저널 — 일간(매일 20:50) / 주간(토 10:00)

git 커밋 기록을 GPT 로 **사용자 관점 변경 안내문**으로 바꿔 `docs/journal/` 에 저장하고
관리자 텔레그램으로 보낸다. 스레드·링크드인 게시글 초안으로 쓰는 글이라 코드 레벨 용어
(파일명·함수명·해시)는 프롬프트에서 금지하고, 의도가 읽히는 변경은 의도를 함께 적는다.

산출물
  일간: docs/journal/daily/YYMMDD.md
  주간: docs/journal/weekly/YYMM-n.md   (n = 그 달의 n번째 월요일이 속한 주)

집계 창 (겹침·누락 없이 하루가 한 파일에만 들어가게)
  일간 D: [D-1 20:50, D 20:50)  — 실행 시각이 아니라 **날짜로 고정**이라 지각 실행해도 내용이 같다.
  주간  : 그 주 토요일 실행 기준으로 **직전 토요일~금요일 일간 파일 7개**를 재요약한다
          (= 커밋 기준 지난주 금 20:50 ~ 이번주 금 20:50). 금 20:50 이후 커밋은 다음 주 몫.

수동 실행
  uv run workers/journal.py --mode daily [--date 2026-08-14] [--no-notify] [--force]
  uv run workers/journal.py --mode weekly [--date 2026-08-15]
  uv run workers/journal.py --backfill            # 첫 커밋~어제까지 일간·주간 일괄 생성(알림 없음)
"""
import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from core.ai_service import complete_json
from core.logging_setup import setup_logging
from core.notifications import send_journal_post

setup_logging()
logger = logging.getLogger("Journal")

REPO_ROOT = Path(__file__).resolve().parents[2]
JOURNAL_DIR = REPO_ROOT / "docs" / "journal"
DAILY_DIR = JOURNAL_DIR / "daily"
WEEKLY_DIR = JOURNAL_DIR / "weekly"

CUTOFF = time(20, 50)        # 일간 집계 경계 (일간 잡 실행 시각과 동일)
MAX_COMMITS = 40             # 하루 프롬프트에 넣을 커밋 상한
MAX_BODY_CHARS = 900         # 커밋 본문 절단
MAX_FILES = 15               # 커밋당 변경 파일 나열 상한
WEEKDAY_KR = ("월", "화", "수", "목", "금", "토", "일")

_SEP_REC, _SEP_FIELD = "\x1e", "\x1f"


# ── 프롬프트 ──
# core/prompts.py 는 콘텐츠 분석 전용 민감 파일(가드)이라 저널 프롬프트는 이 워커가 갖는다.
_COMMON_RULES = """작성 규칙:
- 한국어, 정중한 '합니다' 체.
- 코드 레벨 용어 금지: 파일명·폴더명·함수명·변수명·테이블명·커밋 해시·라이브러리 이름을 쓰지 않는다.
- 서비스를 쓰는 사람이 체감하는 변화로 번역해서 쓴다(무엇이 새로 생겼는지, 무엇이 더 정확·편해졌는지).
- 의도가 읽히는 변경이면 왜 그렇게 했는지 한 문장으로 덧붙인다. 추측이 필요하면 비워 둔다.
- 비슷한 작업 여러 건은 한 항목으로 합친다. 중요한 순서로 정렬한다.
- 겉으로 드러나지 않는 내부 정리·안정화만 있으면 '내부 정리' 한 항목으로 짧게 묶는다.
- 과장·홍보 문구·이모지·해시태그 금지. 사실만 담백하게.
- 각 설명은 1~2문장."""

DAILY_PROMPT = """너는 한국 주식 분석·자동매매 서비스의 변경사항을 사용자에게 알리는 글을 쓰는 편집자다.
아래는 {date_label} 하루 동안의 개발 기록이다. 이걸 사용자 입장의 변경 안내로 바꿔라.

{rules}
- 항목은 최대 5개.

[개발 기록]
{commits}

출력은 아래 JSON 만. 다른 말 금지.
{{"summary": "하루를 한 문장으로", "items": [{{"title": "짧은 제목(공백 포함 20자 내외)", "detail": "1~2문장 설명", "intent": "의도 한 문장(없으면 빈 문자열)"}}]}}"""

WEEKLY_PROMPT = """너는 한국 주식 분석·자동매매 서비스의 주간 변경사항을 사용자에게 알리는 글을 쓰는 편집자다.
아래는 {date_label} 한 주간의 일간 기록이다. 한 주를 관통하는 흐름으로 다시 묶어라.

{rules}
- 항목은 최대 6개. 일간 기록을 그대로 나열하지 말고, 같은 방향의 작업은 하나의 흐름으로 합친다.
- 그 주에 무엇을 개선하려 했는지가 드러나게 쓴다.

[일간 기록]
{dailies}

출력은 아래 JSON 만. 다른 말 금지.
{{"summary": "한 주를 한 문장으로", "items": [{{"title": "짧은 제목(공백 포함 20자 내외)", "detail": "1~2문장 설명", "intent": "의도 한 문장(없으면 빈 문자열)"}}]}}"""


@dataclass
class Commit:
    when: str
    subject: str
    body: str
    files: list[str]

    def as_prompt_block(self) -> str:
        lines = [f"- [{self.when}] {self.subject}"]
        if self.body:
            lines += [f"    {ln}" for ln in self.body.splitlines() if ln.strip()]
        if self.files:
            shown = self.files[:MAX_FILES]
            more = f" 외 {len(self.files) - len(shown)}개" if len(self.files) > len(shown) else ""
            lines.append(f"    (변경 영역: {', '.join(shown)}{more})")
        return "\n".join(lines)


# ── git ──
def _git_log(since: datetime, until: datetime) -> list[Commit]:
    """[since, until) 구간 커밋을 최신순으로 읽는다 (머지 커밋 제외)."""
    fmt = f"{_SEP_REC}%ad{_SEP_FIELD}%s{_SEP_FIELD}%b{_SEP_FIELD}"
    try:
        out = subprocess.run(
            ["git", "log", "--no-merges", "--name-only",
             f"--since={since:%Y-%m-%d %H:%M:%S}", f"--until={until:%Y-%m-%d %H:%M:%S}",
             "--date=format:%Y-%m-%d %H:%M", f"--pretty=format:{fmt}"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        logger.error("git log 실패: %s", e)
        return []

    commits: list[Commit] = []
    for record in out.split(_SEP_REC):
        if not record.strip():
            continue
        parts = record.split(_SEP_FIELD)
        if len(parts) < 4:
            continue
        when, subject, body, tail = parts[0], parts[1], parts[2], parts[3]
        # 서명 줄(Co-Authored-By 등)은 내용이 아니라 잡음이라 뺀다.
        body_lines = [ln for ln in body.strip().splitlines()
                      if not ln.strip().lower().startswith(("co-authored-by", "🤖 generated"))]
        files = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        commits.append(Commit(
            when=when.strip(), subject=subject.strip(),
            body="\n".join(body_lines).strip()[:MAX_BODY_CHARS],
            files=files,
        ))
    return commits


def _first_commit_date() -> date | None:
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--date=format:%Y-%m-%d", "--pretty=format:%ad"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=True,
        ).stdout.splitlines()
        return date.fromisoformat(out[0].strip()) if out else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as e:
        logger.error("첫 커밋 조회 실패: %s", e)
        return None


# ── 렌더 ──
def _render(heading: str, summary: str, items: list[dict], footer: str) -> str:
    parts = [f"# {heading}", ""]
    if summary:
        parts += [summary.strip(), ""]
    for it in items:
        title = (it.get("title") or "").strip()
        detail = (it.get("detail") or "").strip()
        intent = (it.get("intent") or "").strip()
        if not title and not detail:
            continue
        parts.append(f"**{title}**" if title else "**변경**")
        if detail:
            parts.append(detail)
        if intent:
            parts.append(f"_왜: {intent}_")
        parts.append("")
    parts += ["---", footer]
    return "\n".join(parts).rstrip() + "\n"


def _to_plain(md: str) -> str:
    """텔레그램 전송용 평문 — 마크다운 강조 기호만 걷어낸다(파싱 모드 없이 그대로 보낸다)."""
    lines = []
    for ln in md.splitlines():
        s = ln.replace("**", "").replace("_왜:", "왜:").rstrip("_")
        s = s[2:] if s.startswith("# ") else s
        lines.append(s)
    return "\n".join(lines).strip()


def _ask(prompt: str) -> dict | None:
    data = complete_json(prompt)
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    data["items"] = [it for it in items if isinstance(it, dict)]
    return data


# ── 일간 ──
def build_daily(target: date, *, force: bool = False, notify: bool = True) -> bool:
    """target 일자 저널 생성. 커밋이 없거나 실패하면 False."""
    path = DAILY_DIR / f"{target:%y%m%d}.md"
    if path.exists() and not force:
        logger.info("이미 존재 — 스킵: %s", path.name)
        return False

    since = datetime.combine(target - timedelta(days=1), CUTOFF)
    until = datetime.combine(target, CUTOFF)
    commits = _git_log(since, until)
    if not commits:
        logger.info("%s: 커밋 없음 — 생성 안 함", target)
        return False

    blocks = "\n".join(c.as_prompt_block() for c in commits[:MAX_COMMITS])
    label = f"{target:%Y년 %m월 %d일}({WEEKDAY_KR[target.weekday()]})"
    data = _ask(DAILY_PROMPT.format(date_label=label, rules=_COMMON_RULES, commits=blocks))
    if not data:
        logger.error("%s: GPT 요약 실패", target)
        return False

    md = _render(
        f"{target:%Y-%m-%d}({WEEKDAY_KR[target.weekday()]}) 변경사항",
        data.get("summary", ""), data["items"], f"작업 {len(commits)}건",
    )
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    logger.info("✔ 일간 저널 작성: %s (커밋 %d건)", path.name, len(commits))
    if notify:
        send_journal_post(_to_plain(md))
    return True


# ── 주간 ──
def _week_bounds(run_day: date) -> tuple[date, date, date]:
    """토요일 실행 기준 (집계 시작=직전 토요일, 끝=어제 금요일, 라벨용 월요일)."""
    friday = run_day - timedelta(days=1)
    start_sat = friday - timedelta(days=6)
    monday = friday - timedelta(days=4)
    return start_sat, friday, monday


def _week_tag(monday: date) -> str:
    """YYMM-n — 그 주 월요일이 속한 달의 n번째 주(월요일 기준)."""
    return f"{monday:%y%m}-{(monday.day - 1) // 7 + 1}"


def build_weekly(run_day: date, *, force: bool = False, notify: bool = True) -> bool:
    start_sat, friday, monday = _week_bounds(run_day)
    path = WEEKLY_DIR / f"{_week_tag(monday)}.md"
    if path.exists() and not force:
        logger.info("이미 존재 — 스킵: %s", path.name)
        return False

    chunks, days = [], 0
    d = start_sat
    while d <= friday:
        f = DAILY_DIR / f"{d:%y%m%d}.md"
        if f.exists():
            chunks.append(f"## {d:%m월 %d일}({WEEKDAY_KR[d.weekday()]})\n{f.read_text(encoding='utf-8')}")
            days += 1
        d += timedelta(days=1)
    if not chunks:
        logger.info("%s~%s: 일간 기록 없음 — 주간 생성 안 함", start_sat, friday)
        return False

    label = f"{start_sat:%Y년 %m월 %d일}~{friday:%m월 %d일}"
    data = _ask(WEEKLY_PROMPT.format(date_label=label, rules=_COMMON_RULES, dailies="\n\n".join(chunks)))
    if not data:
        logger.error("%s: GPT 주간 요약 실패", path.name)
        return False

    md = _render(
        f"{_week_tag(monday)} 주간 변경사항 ({start_sat:%m/%d}~{friday:%m/%d})",
        data.get("summary", ""), data["items"], f"기록된 작업일 {days}일",
    )
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    logger.info("✔ 주간 저널 작성: %s (일간 %d건 종합)", path.name, days)
    if notify:
        send_journal_post(_to_plain(md))
    return True


# ── 백필 ──
def backfill(force: bool = False) -> int:
    """첫 커밋일~어제까지 일간을 채우고, 완성된 주(지난 토요일까지)의 주간을 채운다."""
    first = _first_commit_date()
    if not first:
        return 1
    today = date.today()
    made_d = made_w = 0

    d = first
    while d < today:
        if build_daily(d, force=force, notify=False):
            made_d += 1
        d += timedelta(days=1)

    # 각 토요일 실행분을 재현 — 첫 커밋 이후 첫 토요일부터 오늘 이전까지
    sat = first + timedelta(days=(5 - first.weekday()) % 7)
    while sat <= today:
        if build_weekly(sat, force=force, notify=False):
            made_w += 1
        sat += timedelta(days=7)

    logger.info("백필 완료 — 일간 %d건, 주간 %d건", made_d, made_w)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="변경사항 저널(일간·주간)")
    p.add_argument("--mode", choices=["daily", "weekly"], help="생성 모드")
    p.add_argument("--date", help="기준일 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--backfill", action="store_true", help="과거 커밋 일괄 생성(알림 없음)")
    p.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    p.add_argument("--no-notify", action="store_true", help="텔레그램 전송 생략")
    args = p.parse_args()

    if args.backfill:
        return backfill(force=args.force)
    if not args.mode:
        p.error("--mode 또는 --backfill 이 필요하다")

    target = date.fromisoformat(args.date) if args.date else date.today()
    notify = not args.no_notify
    if args.mode == "daily":
        build_daily(target, force=args.force, notify=notify)
    else:
        build_weekly(target, force=args.force, notify=notify)
    # 커밋이 없는 날도 정상 종료(exit 0) — 스케줄러 실패 경보는 잡 오류에만 뜨게 한다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
