#!/usr/bin/env python3
"""Generate Claude and Codex project configuration from .agent-config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".agent-config"


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: YAML frontmatter가 없습니다")
    try:
        raw_metadata, body = text[4:].split("\n---\n", 1)
    except ValueError as error:
        raise ValueError(f"{path}: YAML frontmatter 종료 구분자가 없습니다") from error

    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"{path}: frontmatter 항목을 해석할 수 없습니다: {line}")
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, body


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def codex_agent(metadata: dict[str, str], body: str) -> str:
    required = {"name", "description"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"Codex 에이전트 필수 항목 누락: {', '.join(sorted(missing))}")
    instructions = body.strip() + "\n"
    return (
        f"# Generated from .agent-config/agents/{metadata['name']}.md.\n"
        f"name = {json.dumps(metadata['name'], ensure_ascii=False)}\n"
        f"description = {json.dumps(metadata['description'], ensure_ascii=False)}\n"
        f"developer_instructions = {json.dumps(instructions, ensure_ascii=False)}\n"
    )


def claude_settings(manifest: dict) -> dict:
    flags = manifest["hooks"]
    hooks: dict[str, list[dict]] = {}

    if flags["sync_on_session_start"]:
        hooks["SessionStart"] = [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": 'python3 "$CLAUDE_PROJECT_DIR/.agent-config/sync.py" --quiet',
                    }
                ],
            }
        ]
    if flags["guard_sensitive"]:
        hooks["PreToolUse"] = [
            {
                "matcher": "Edit|Write|NotebookEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/guard-sensitive.sh",
                    }
                ],
            }
        ]

    post_handlers: list[dict] = []
    if flags["quality_after_edit"]:
        post_handlers.extend(
            [
                {
                    "type": "command",
                    "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/quality-gate.sh",
                },
                {
                    "type": "command",
                    "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/track-changes.sh",
                },
            ]
        )
    if flags["sync_after_edit"]:
        post_handlers.append(
            {
                "type": "command",
                "command": 'python3 "$CLAUDE_PROJECT_DIR/.agent-config/sync.py" --quiet',
            }
        )
    if post_handlers:
        hooks["PostToolUse"] = [{"matcher": "Edit|Write", "hooks": post_handlers}]

    if flags["deploy_on_stop"]:
        hooks["Stop"] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/deploy-on-stop.sh",
                    }
                ]
            }
        ]
    # claude_settings: settings.json 최상위 키 그대로 통과 (예: includeCoAuthoredBy)
    return {
        "permissions": manifest["claude_permissions"],
        "hooks": hooks,
        **manifest.get("claude_settings", {}),
    }


def codex_hooks(manifest: dict) -> dict:
    flags = manifest["hooks"]
    hooks: dict[str, list[dict]] = {}
    root_expr = "$(git rev-parse --show-toplevel)"

    if flags["sync_on_session_start"]:
        hooks["SessionStart"] = [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": f'/usr/bin/python3 "{root_expr}/.agent-config/sync.py" --quiet',
                        "timeout": 60,
                        "statusMessage": "Claude/Codex 설정 동기화",
                    }
                ],
            }
        ]
    if flags["guard_sensitive"]:
        hooks["PreToolUse"] = [
            {
                "matcher": "Read|Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": f'/usr/bin/python3 "{root_expr}/.codex/hooks/edit_hook.py" guard',
                        "timeout": 30,
                        "statusMessage": "민감 파일 변경 여부 확인",
                    }
                ],
            }
        ]

    post_handlers: list[dict] = []
    if flags["quality_after_edit"]:
        post_handlers.append(
            {
                "type": "command",
                "command": f'/usr/bin/python3 "{root_expr}/.codex/hooks/edit_hook.py" post',
                "timeout": 300,
                "statusMessage": "변경 파일 품질 검사",
            }
        )
    if flags["sync_after_edit"]:
        post_handlers.append(
            {
                "type": "command",
                "command": f'/usr/bin/python3 "{root_expr}/.agent-config/sync.py" --quiet',
                "timeout": 60,
                "statusMessage": "Claude/Codex 설정 동기화",
            }
        )
    if post_handlers:
        hooks["PostToolUse"] = [{"matcher": "Edit|Write", "hooks": post_handlers}]

    if flags["deploy_on_stop"]:
        hooks["Stop"] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f'/usr/bin/env bash "{root_expr}/.codex/hooks/deploy-on-stop.sh"',
                        "timeout": 600,
                        "statusMessage": "변경된 서비스 빌드 및 반영",
                    }
                ]
            }
        ]
    return {
        "description": "Generated from .agent-config; do not edit this file directly.",
        "hooks": hooks,
    }


def codex_rules(manifest: dict) -> str:
    lines = ["# Generated from .agent-config/manifest.json; do not edit directly.", ""]
    for rule in manifest["codex_rules"]:
        pattern = json.dumps(rule["pattern"], ensure_ascii=False)
        decision = json.dumps(rule["decision"], ensure_ascii=False)
        justification = json.dumps(rule["justification"], ensure_ascii=False)
        lines.extend(
            [
                "prefix_rule(",
                f"    pattern = {pattern},",
                f"    decision = {decision},",
                f"    justification = {justification},",
                ")",
                "",
            ]
        )
    return "\n".join(lines)


def expected_outputs(manifest: dict) -> dict[Path, str]:
    outputs: dict[Path, str] = {}

    skill_root = SOURCE / "skills"
    for source_skill in sorted(skill_root.glob("*/SKILL.md")):
        skill_dir = source_skill.parent
        skill_name = skill_dir.name
        metadata, _ = parse_frontmatter(source_skill)
        if metadata.get("name") != skill_name:
            raise ValueError(f"{source_skill}: 폴더명과 skill name이 다릅니다")
        skill_text = source_skill.read_text(encoding="utf-8")
        outputs[ROOT / ".claude" / "skills" / skill_name / "SKILL.md"] = skill_text
        outputs[ROOT / ".agents" / "skills" / skill_name / "SKILL.md"] = skill_text

        openai_yaml = skill_dir / "agents" / "openai.yaml"
        if not openai_yaml.is_file():
            raise ValueError(f"{openai_yaml}: Codex UI 메타데이터가 없습니다")
        outputs[ROOT / ".agents" / "skills" / skill_name / "agents" / "openai.yaml"] = openai_yaml.read_text(
            encoding="utf-8"
        )

    for source_agent in sorted((SOURCE / "agents").glob("*.md")):
        metadata, body = parse_frontmatter(source_agent)
        name = metadata.get("name")
        if not name or source_agent.stem != name:
            raise ValueError(f"{source_agent}: 파일명과 agent name이 다릅니다")
        outputs[ROOT / ".claude" / "agents" / source_agent.name] = source_agent.read_text(encoding="utf-8")
        outputs[ROOT / ".codex" / "agents" / f"{name}.toml"] = codex_agent(metadata, body)

    outputs[ROOT / ".claude" / "settings.json"] = json_text(claude_settings(manifest))
    outputs[ROOT / ".codex" / "hooks.json"] = json_text(codex_hooks(manifest))
    outputs[ROOT / ".codex" / "config.toml"] = (
        "# Generated from .agent-config/manifest.json; do not edit directly.\n"
        "[features]\n"
        "hooks = true\n"
    )
    outputs[ROOT / ".codex" / "rules" / "default.rules"] = codex_rules(manifest)
    return outputs


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def synchronize(check: bool, quiet: bool) -> int:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("지원하지 않는 .agent-config manifest version입니다")

    changed: list[Path] = []
    for path, content in expected_outputs(manifest).items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        changed.append(path.relative_to(ROOT))
        if not check:
            write_atomic(path, content)

    if check and changed:
        print("동기화되지 않은 생성 파일:")
        for path in changed:
            print(f"- {path}")
        return 1
    if not quiet:
        if changed:
            action = "갱신 필요" if check else "동기화 완료"
            print(f"{action}: {len(changed)}개 파일")
            for path in changed:
                print(f"- {path}")
        else:
            print("Claude/Codex 설정이 공통 원본과 일치합니다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="드리프트만 검사하고 파일은 쓰지 않는다")
    parser.add_argument("--quiet", action="store_true", help="변경이 없거나 성공한 경우 출력을 생략한다")
    args = parser.parse_args()
    return synchronize(check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
