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

# 화면(프론트) 코드 변경이면 모바일 우선 가이드를 컨텍스트로 주입.
# 백엔드 주요 로직(core/routers/workers/api.py) 변경이면 해당 README 동기화를 상기.
README=""
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
  *jongalab/core/*|*jongalab/routers/*|*jongalab/workers/*|*jongalab/api.py)  README="jongalab/README.md" ;;
  *trading/core/*|*trading/routers/*|*trading/workers/*|*trading/api.py)      README="trading/README.md" ;;
  *kiwoom/core/*|*kiwoom/workers/*|*kiwoom/api.py)                            README="kiwoom/README.md" ;;
esac

# 백엔드 주요 로직이면 README 동기화 가이드를 컨텍스트로 주입
if [ -n "$README" ]; then
  README="$README" python3 - <<'PY'
import json, os
rd = os.environ.get("README", "README.md")
msg = (
    f"📄 주요 로직(core/routers/workers)을 변경했습니다. `{rd}` 는 이 도메인의 소스 오브 트루스입니다.\n"
    f"- 아직 안 읽었다면 `{rd}` 를 먼저 읽어 구조·흐름·안전장치를 확인하세요.\n"
    f"- 책임/흐름/엔드포인트/안전장치가 바뀌었다면 이번 턴에 `{rd}` 도 함께 갱신하세요(코드-문서 불일치로 완료 보고 금지).\n"
    "- 작성 전 5원칙(필요성·기존 코드 재사용·최단 구조·최소 혼란 흐름·유지보수성)을 먼저 따졌는지 점검하세요."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg
    }
}))
PY
fi

exit 0
