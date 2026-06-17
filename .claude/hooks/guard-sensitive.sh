#!/usr/bin/env bash
# PreToolUse 가드: 민감/미추적 파일 편집을 차단한다.
# stdin 으로 tool 입력 JSON 을 받는다. exit 2 = 도구 호출 차단(+stderr 를 Claude 에 전달).
set -euo pipefail

FILE=$(python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")
' 2>/dev/null || echo "")

case "$FILE" in
  *core/trading_engine.py|*core/prompts.py)
    echo "🚫 $FILE 는 git 미추적 민감 로직입니다. 변경은 복구·공유 불가합니다." >&2
    echo "   수정이 정말 필요하면 사용자에게 명시적으로 확인받은 뒤, 변경 내용을 설명하고 진행하세요." >&2
    exit 2
    ;;
  *trading/core/risk_engine.py|*trading/core/execution_engine.py)
    echo "🚫 $FILE 는 자금 손실에 직결되는 민감 로직(리스크 한도·주문 집행)입니다." >&2
    echo "   수정 전 사용자에게 명시적으로 확인받고, 변경 내용을 설명한 뒤 진행하세요." >&2
    exit 2
    ;;
  *.env|*.session|*.session-journal)
    echo "🚫 $FILE 는 비밀/세션 파일입니다. 편집·커밋 금지." >&2
    exit 2
    ;;
esac

exit 0
