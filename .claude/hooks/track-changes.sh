#!/usr/bin/env bash
# PostToolUse: 편집된 파일을 누적 기록하고(턴 종료 시 deploy-on-stop 이 소비),
# 프론트(화면) 파일이면 "모바일 최우선" 가이드를 Claude 컨텍스트에 주입한다.
# - 누적 기록: .claude/.pending-changes (gitignore)
# - exit 0 고정(검증 책임은 quality-gate.sh 가 따로 담당). 여긴 기록/상기 전용.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PENDING="$ROOT/.claude/.pending-changes"

FILE=$(python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")
' 2>/dev/null || echo "")

[ -z "$FILE" ] && exit 0

# 변경 파일 누적 (절대경로)
echo "$FILE" >> "$PENDING"

# 화면(프론트) 코드 변경이면 모바일 우선 가이드를 컨텍스트로 주입
case "$FILE" in
  *frontend/*.ts|*frontend/*.tsx|*frontend/*.css)
    python3 - <<'PY'
import json
msg = (
    "📱 화면(프론트) 코드를 변경했습니다. 이 대시보드는 모바일에서 자주 쓰입니다.\n"
    "- 작은 화면을 먼저 만족시키고 sm:/md: 로 확장하세요 (데스크탑만 보고 끝내지 말 것).\n"
    "- 터치 타깃·가독성·가로 스크롤 여부를 모바일 폭(≈375px) 기준으로 점검하세요.\n"
    "- 턴 종료 시 jongalab-fe 이 자동으로 'npm run build' 후 재시작됩니다 (빌드 실패 시 알림)."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg
    }
}))
PY
    ;;
esac

exit 0
