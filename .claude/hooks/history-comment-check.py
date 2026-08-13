#!/usr/bin/env python3
"""편집한 파일에 **이력성 주석**이 새로 들어갔는지 검사한다 (경고 전용, 차단하지 않음).

규칙(AGENTS.md "문서 세 계층"):
  코드 주석      = 지금 코드가 무엇을 하는가 + 왜 이 값/구조인가(결론 한 줄)
  README.md      = 현재 구조·상태
  docs/history/  = 날짜·백테스트 수치·기각 근거·사고 경위(변경 서사)

Claude(.claude/hooks/track-changes.sh)와 Codex(.codex/hooks/edit_hook.py)가 이 파일을
공유해 같은 판정을 쓴다. 패턴을 고칠 땐 여기만 고친다.

사용법: python3 history-comment-check.py <file> [file...]
  → 이력성 주석이 새로 추가됐으면 경고 문구를 stdout 으로 출력(없으면 무출력). 항상 exit 0.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# 검사 대상 — 코드 파일만. sql 마이그레이션은 그 자체가 날짜 박힌 이력 산출물이라 제외한다.
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIP_PARTS = {"node_modules", ".next", "__pycache__", "sql", "tests", "docs", ".claude", ".codex"}

COMMENT_HEAD = re.compile(r'^\s*(#|//|/\*|\*|"""|\'\'\')')
# 줄 끝 주석(`X = 1  # 예전엔 2`)도 같은 규칙을 받는다.
COMMENT_TAIL = re.compile(r"\s(#|//)\s")

# ① 변경 서사 — "예전엔 X 였다 / 제거했다 / 되돌렸다"
NARRATIVE = re.compile(
    r"(예전엔|예전에는|예전 |이전엔|이전에는|과거엔|종전의|제거했|삭제했|폐지|되돌렸|되돌림"
    r"|롤백했|교체했|전환했|재도입|재설계했|바꿨다|없앴다|차 실패|오탐 사고)"
)
# ② 근거 덤프 — 백테스트 표본·유의성·실측 수치
EVIDENCE = re.compile(r"(백테스트|t\s?=\s?[+-]?\d|n\s?=\s?\d|승률\s?\d|표본\s?\d|%p\b|거래일\s?\d+\s?일\b)")

HINT = (
    "⚠️ 이력성 주석이 코드에 새로 들어갔습니다. 코드 주석은 **현재 동작과 그 이유 한 줄**만 담습니다.\n"
    "   변경 서사(예전엔 X 였다·제거했다)·백테스트 수치·사고 경위는 `docs/history/<축>.md` 로 옮기고,\n"
    "   코드에는 결론 한 줄 + 포인터(예: `# 근거: docs/history/edge-ledger.md`)만 남기세요.\n"
    "   축: selection-scoring · edge-ledger · news-pipeline · execution-exit · gates-sizing · infra-incidents · frontend-ui\n"
    "   (도입 시점 태그 `(2026-07-19, sql/25)` 처럼 추적용 출처 표기는 그대로 둬도 됩니다.)"
)


def added_lines(path: Path, root: Path) -> list[str]:
    """working tree 기준으로 이번에 추가된 줄. git 밖(미추적) 파일이면 전체를 본다."""
    result = subprocess.run(
        ["git", "diff", "-U0", "HEAD", "--", str(path)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return []
    diff = result.stdout
    if not diff.strip():
        # 미추적 파일(git 이 diff 를 못 냄) — 새 파일이므로 전체를 검사한다.
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if tracked.returncode != 0:
            try:
                return path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        return []
    return [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]


def offenders(lines: list[str]) -> list[str]:
    hits = []
    for line in lines:
        if COMMENT_HEAD.match(line):
            comment = line
        else:
            tail = COMMENT_TAIL.search(line)
            if not tail:
                continue
            comment = line[tail.start():]
        if "docs/history/" in comment:
            continue  # 이력으로 넘긴 뒤 남긴 포인터 — 이게 정답 형태다.
        if NARRATIVE.search(comment) or EVIDENCE.search(comment):
            hits.append(line.strip())
    return hits


def main() -> int:
    root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if root_result.returncode != 0:
        return 0
    root = Path(root_result.stdout.strip())

    report: list[str] = []
    for raw in sys.argv[1:]:
        path = Path(raw)
        if path.suffix not in CODE_SUFFIXES or SKIP_PARTS & set(path.parts):
            continue
        if not path.is_file():
            continue
        hits = offenders(added_lines(path, root))
        if not hits:
            continue
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        report.append(f"· {shown}")
        report.extend(f"    {h[:110]}" for h in hits[:5])
        if len(hits) > 5:
            report.append(f"    … 외 {len(hits) - 5}줄")

    if report:
        print(HINT)
        print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
