#!/usr/bin/env bash
# PostToolUse: 편집된 파일을 누적 기록하고(턴 종료 시 deploy-on-stop 이 소비),
# 프론트(화면) 파일이면 "모바일 최우선" 가이드를 Claude 컨텍스트에 주입한다.
# 또한 이번 편집으로 **이력성 주석**이 코드에 들어갔으면 경고를 함께 주입한다.
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

# 화면(프론트) 코드 변경이면 모바일 우선 가이드를, 백엔드 주요 로직(core/routers/workers/api.py)
# 변경이면 해당 README 동기화를 상기한다. 두 가이드와 아래 이력 주석 경고를 한 번에 주입한다.
KIND=""
README=""
case "$FILE" in
  *frontend/*.ts|*frontend/*.tsx|*frontend/*.css)                              KIND="frontend" ;;
  *jongalab/core/*|*jongalab/routers/*|*jongalab/workers/*|*jongalab/api.py)  README="jongalab/README.md" ;;
  *trading/core/*|*trading/routers/*|*trading/workers/*|*trading/api.py)      README="trading/README.md" ;;
  *kiwoom/core/*|*kiwoom/workers/*|*kiwoom/api.py)                            README="kiwoom/README.md" ;;
esac

# 이력성 주석 경고(경고 전용, 차단하지 않음). 판정 기준은 history-comment-check.py 가 단일 소스.
HISTORY_WARN=$(python3 "$ROOT/.claude/hooks/history-comment-check.py" "$FILE" 2>/dev/null || echo "")

KIND="$KIND" README="$README" HISTORY_WARN="$HISTORY_WARN" python3 - <<'PY'
import json, os

parts = []
if os.environ.get("KIND") == "frontend":
    parts.append(
        "📱 화면(프론트) 코드를 변경했습니다. 이 대시보드는 모바일에서 자주 쓰입니다.\n"
        "- 작은 화면을 먼저 만족시키고 sm:/md: 로 확장하세요 (데스크탑만 보고 끝내지 말 것).\n"
        "- 터치 타깃·가독성·가로 스크롤 여부를 모바일 폭(≈375px) 기준으로 점검하세요.\n"
        "- 화면 구성·규칙이 바뀌면 `jongalab/frontend/README.md`(현재 상태)를 갱신하고,"
        " 재설계 경위·실측 수치는 `docs/history/frontend-ui.md` 에 남기세요(README 에 이력 금지).\n"
        "- 📚 UI 오독 사고 이력(미검증 라벨 색·표시 순번·진행바 불일치)이 `docs/history/frontend-ui.md` 에 있습니다.\n"
        "- 턴 종료 시 jongalab-fe 이 자동으로 'npm run build' 후 재시작됩니다 (빌드 실패 시 알림)."
    )
rd = os.environ.get("README") or ""
if rd:
    parts.append(
        f"📄 주요 로직(core/routers/workers)을 변경했습니다. `{rd}` 는 이 도메인의 소스 오브 트루스입니다.\n"
        f"- 아직 안 읽었다면 `{rd}` 를 먼저 읽어 구조·흐름·안전장치를 확인하세요.\n"
        f"- 책임/흐름/엔드포인트/안전장치가 바뀌었다면 이번 턴에 `{rd}` 도 함께 갱신하세요(코드-문서 불일치로 완료 보고 금지).\n"
        "- 📚 `docs/history/` 에 이 축의 판정 이력이 있습니다. **손대는 축의 파일을 먼저 확인해**"
        " 이미 기각된 방향을 다시 제안하지 않게 하세요"
        "(selection-scoring · edge-ledger · news-pipeline · execution-exit · gates-sizing · infra-incidents).\n"
        f"- ⚠️ 세 계층: 코드 주석 = **현재 동작·이유 한 줄** / `{rd}` = **현재 구조·상태** /"
        " `docs/history/<축>.md` = **날짜·백테스트 수치·기각 근거·사고 경위**. 이력을 코드나 README 에 쓰지 마세요.\n"
        "- 작성 전 5원칙(필요성·기존 코드 재사용·최단 구조·최소 혼란 흐름·유지보수성)을 먼저 따졌는지 점검하세요."
    )
warn = (os.environ.get("HISTORY_WARN") or "").strip()
if warn:
    parts.append(warn)

if parts:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(parts),
        }
    }))
PY

exit 0
