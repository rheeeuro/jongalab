---
name: check
description: 프론트엔드 타입·린트와 Python 문법 및 관련 단위 테스트를 한 번에 검증한다. 사용자가 변경 사항 점검, 품질 게이트, 커밋·PR 전 확인, 또는 Claude의 /check와 같은 검증을 요청할 때 사용한다.
---

# 변경 사항 검증

1. `python3 .agent-config/sync.py --check`로 Claude/Codex 설정 드리프트를 확인한다.
2. `git status --short`와 `git diff --stat`로 변경 범위를 확인한다.
3. 변경된 `.ts`·`.tsx`가 있으면 해당 프론트엔드에서 다음을 실행한다.
   - `cd jongalab/frontend && npx tsc --noEmit && npm run lint`
   - `trading/frontend` 변경이면 그 디렉터리에서도 같은 검증을 실행한다.
4. 변경된 `.py`마다 파일이 속한 서브프로젝트를 기준으로 실행한다.
   - `uv run --directory <jongalab|kiwoom|trading> python -m py_compile <상대경로>`
5. 동작이 바뀐 순수 로직은 `AGENTS.md`에 지정된 관련 pytest 명령도 실행한다.
6. 라우터나 API 응답이 바뀌었으면 API 실행 스킬로 실제 응답 상태와 shape를 확인한다.
7. 실패를 수정하고 같은 검증을 다시 통과시킨 뒤에만 완료로 보고한다.

각 명령의 실행 결과를 통과·실패로 간결하게 요약한다. 추측으로 통과를 보고하지 않는다.
