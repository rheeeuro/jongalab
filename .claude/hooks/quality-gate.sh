#!/usr/bin/env bash
# PostToolUse 품질 게이트: 편집된 파일 종류에 맞춰 빠른 검증을 돌린다.
# exit 2 = 실패를 Claude 에 피드백(stderr). exit 0 = 통과/대상 아님.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

FILE=$(python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")
' 2>/dev/null || echo "")

[ -z "$FILE" ] && exit 0

case "$FILE" in
  *frontend/*.ts|*frontend/*.tsx)
    OUT=$(cd "$ROOT/jongalab/frontend" && npx tsc --noEmit 2>&1)
    if [ $? -ne 0 ]; then
      echo "❌ tsc 타입 체크 실패 (frontend):" >&2
      echo "$OUT" | tail -30 >&2
      exit 2
    fi
    ;;
  *.py)
    # 파일이 속한 서브프로젝트(jongalab/kiwoom/trading)에서 컴파일한다(루트는 더 이상 uv 프로젝트 아님).
    # 주의: 리포지토리 루트 디렉터리명이 'jongalab' 이므로 trading/kiwoom 을 먼저 매칭해야 한다.
    case "$FILE" in
      */trading/*) SUB="trading";  REL="${FILE##*/trading/}" ;;
      */kiwoom/*)  SUB="kiwoom";   REL="${FILE##*/kiwoom/}" ;;
      */jongalab/*) SUB="jongalab"; REL="${FILE##*/jongalab/}" ;;
      *) exit 0 ;;
    esac
    OUT=$(uv run --directory "$ROOT/$SUB" python -m py_compile "$REL" 2>&1)
    if [ $? -ne 0 ]; then
      echo "❌ Python 컴파일 실패: $SUB/$REL" >&2
      echo "$OUT" | tail -20 >&2
      exit 2
    fi
    ;;
esac

exit 0
