#!/usr/bin/env python3
"""Bridge Codex edit hook payloads to jongalab's project checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete|Move to) File: (.+)$", re.MULTILINE)
SENSITIVE_LOGIC = {
    "jongalab/core/trading_engine.py",
    "jongalab/core/prompts.py",
    "trading/core/risk_engine.py",
    "trading/core/execution_engine.py",
}
PROTECTED_DIRS = {"mariadb_data", "ollama_data"}
GENERATED_FILES = {
    ".claude/settings.json",
    ".codex/config.toml",
    ".codex/hooks.json",
}
GENERATED_PREFIXES = (
    ".claude/skills/",
    ".claude/agents/",
    ".agents/skills/",
    ".codex/agents/",
    ".codex/rules/",
)


def load_payload() -> dict:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def project_root(payload: dict) -> Path:
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else cwd


def changed_paths(payload: dict, root: Path) -> list[Path]:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return []

    raw_paths: list[str] = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            raw_paths.append(value)

    patch = tool_input.get("input") or tool_input.get("patch") or ""
    if isinstance(patch, str):
        raw_paths.extend(PATCH_FILE_RE.findall(patch))

    paths: list[Path] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = Path(raw_path.strip())
        path = path.resolve() if path.is_absolute() else (root / path).resolve()
        marker = str(path)
        if marker not in seen:
            seen.add(marker)
            paths.append(path)
    return paths


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def guard(paths: list[Path], root: Path) -> int:
    for path in paths:
        relative = relative_path(path, root)
        parts = set(Path(relative).parts)
        if relative in GENERATED_FILES or relative.startswith(GENERATED_PREFIXES):
            message = f"🚫 {relative}는 .agent-config/에서 생성됩니다. 공통 원본을 수정하세요."
        elif relative in SENSITIVE_LOGIC:
            message = f"🚫 {relative}는 민감 로직입니다. 수정 전 사용자 확인이 필요합니다."
        elif path.name == ".env" or path.name.endswith((".session", ".session-journal")):
            message = f"🚫 {relative}는 비밀/세션 파일입니다. 읽기·편집·커밋할 수 없습니다."
        elif parts & PROTECTED_DIRS:
            message = f"🚫 {relative}는 보호된 데이터 디렉터리입니다. 읽거나 수정할 수 없습니다."
        else:
            continue

        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
        print(message, file=sys.stderr)
        return 2
    return 0


def run_check(command: list[str], cwd: Path, label: str) -> str | None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=280)
    if result.returncode == 0:
        return None
    output = (result.stdout + "\n" + result.stderr).strip().splitlines()
    return f"❌ {label} 실패:\n" + "\n".join(output[-30:])


def python_check(path: Path, root: Path) -> str | None:
    relative = relative_path(path, root)
    for project in ("trading", "kiwoom", "jongalab"):
        prefix = f"{project}/"
        if relative.startswith(prefix):
            project_relative = relative.removeprefix(prefix)
            return run_check(
                ["uv", "run", "--directory", project, "python", "-m", "py_compile", project_relative],
                root,
                f"Python 문법 검사 ({relative})",
            )
    return None


def post_edit(paths: list[Path], root: Path) -> int:
    if not paths:
        return 0

    pending = root / ".codex" / ".pending-changes"
    with pending.open("a", encoding="utf-8") as handle:
        for path in paths:
            handle.write(f"{path}\n")

    failures: list[str] = []
    reminders: list[str] = []
    relative_paths = [relative_path(path, root) for path in paths]

    if any(path.startswith("jongalab/frontend/") and path.endswith((".ts", ".tsx")) for path in relative_paths):
        failure = run_check(["npx", "tsc", "--noEmit"], root / "jongalab" / "frontend", "tsc (jongalab/frontend)")
        if failure:
            failures.append(failure)

    if any(path.startswith("trading/frontend/") and path.endswith((".ts", ".tsx")) for path in relative_paths):
        failure = run_check(["npx", "tsc", "--noEmit"], root / "trading" / "frontend", "tsc (trading/frontend)")
        if failure:
            failures.append(failure)

    for path in paths:
        if path.suffix == ".py":
            failure = python_check(path, root)
            if failure:
                failures.append(failure)

    if any("/frontend/" in f"/{path}" and path.endswith((".ts", ".tsx", ".css")) for path in relative_paths):
        reminders.append("📱 모바일 폭(약 375px)의 가독성·터치 타깃·가로 스크롤을 우선 점검하세요.")

    readmes: set[str] = set()
    for path in relative_paths:
        if path == "jongalab/api.py" or path.startswith(("jongalab/core/", "jongalab/routers/", "jongalab/workers/")):
            readmes.add("jongalab/README.md")
        elif path == "trading/api.py" or path.startswith(("trading/core/", "trading/routers/", "trading/workers/")):
            readmes.add("trading/README.md")
        elif path == "kiwoom/api.py" or path.startswith(("kiwoom/core/", "kiwoom/workers/")):
            readmes.add("kiwoom/README.md")
    if readmes:
        reminders.append("📄 주요 로직 변경입니다. 구조·흐름·안전장치가 바뀌었다면 " + ", ".join(sorted(readmes)) + "도 동기화하세요.")

    # 이력성 주석 경고 — 판정 기준은 .claude/hooks/history-comment-check.py 가 단일 소스(Claude 와 공유).
    history = subprocess.run(
        ["/usr/bin/env", "python3", str(root / ".claude" / "hooks" / "history-comment-check.py"), *[str(p) for p in paths]],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if history.returncode == 0 and history.stdout.strip():
        reminders.append(history.stdout.strip())

    messages = failures + reminders
    if messages:
        message = "\n".join(messages)
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))
        if failures:
            print(message, file=sys.stderr)
            return 2
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"guard", "post"}:
        print("usage: edit_hook.py <guard|post>", file=sys.stderr)
        return 2
    payload = load_payload()
    root = project_root(payload)
    paths = changed_paths(payload, root)
    return guard(paths, root) if sys.argv[1] == "guard" else post_edit(paths, root)


if __name__ == "__main__":
    raise SystemExit(main())
