#!/usr/bin/env bash
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
export CLAUDE_PROJECT_DIR="$ROOT"
export AGENT_PENDING_CHANGES="$ROOT/.codex/.pending-changes"
export CODEX_HOOK=1

exec "$ROOT/.claude/hooks/deploy-on-stop.sh"
