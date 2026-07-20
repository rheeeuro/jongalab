# Claude/Codex 공통 설정 변경 가이드

이 디렉터리는 두 에이전트 하네스의 단일 원본이다. 변경 전에 루트 `AGENTS.md`와 이 파일을 함께 읽는다.

## 기본 원칙

- `.agent-config/`만 직접 수정한다. `.claude/skills/`, `.claude/agents/`, `.claude/settings.json`,
  `.agents/skills/`, `.codex/agents/`, `.codex/config.toml`, `.codex/hooks.json`, `.codex/rules/`는 생성물이다.
- 공통 의미를 먼저 설계한 뒤 Claude와 Codex의 형식 차이는 `sync.py`의 생성 어댑터에서만 처리한다.
- 설정 변경을 제품 코드 변경과 섞지 않는다. 필요한 파일만 좁게 수정하고 무관한 정리·리포맷을 하지 않는다.
- `.claude/settings.local.json`, 글로벌 `~/.codex/`, 개인 경로·계정·SSH·토큰 설정은 공통 원본에 넣지 않는다.
- `.env`, 세션 파일, 데이터 볼륨을 읽거나 설정·예시·로그에 비밀값을 복사하지 않는다.

## 전문 에이전트

- `.agent-config/agents/<name>.md`의 파일명과 frontmatter `name`을 일치시킨다. 이름은 호출 식별자이므로
  불필요하게 바꾸지 않는다.
- `description`에는 담당 범위와 호출 시점을 구체적으로 쓰고, 본문에는 그 역할에만 필요한 규칙을 둔다.
  루트 `AGENTS.md`의 공통 규칙을 약화하거나 상충시키지 않는다.
- `tools`는 최소 권한으로 유지한다. 쓰기·셸·네트워크·외부 시스템 접근을 넓히기 전에는 사용자에게
  변경 범위와 위험을 설명하고 명시적으로 확인받는다.
- 검증 전담 에이전트처럼 읽기 중심 역할에는 코드 수정 금지를 유지한다. 역할 설명만으로 권한이 강제된다고
  가정하지 말고 샌드박스·훅·상위 지침도 함께 점검한다.
- 이름을 바꾸거나 원본을 삭제해도 `sync.py`는 기존 생성물을 자동 삭제하지 않는다. 참조 위치와 남은 생성물을
  먼저 찾고, 정확한 삭제 대상에 대해 확인한 뒤 정리한다.

## 스킬

- `.agent-config/skills/<name>/SKILL.md`의 폴더명과 frontmatter `name`을 일치시키고 소문자 하이픈 형식을 쓴다.
- frontmatter에는 `name`과 `description`만 둔다. `description`에는 기능과 구체적인 호출 조건을 모두 포함한다.
- 본문은 Claude와 Codex 모두 이해할 수 있게 플랫폼 중립적으로 작성한다. `/command`나 `$skill` 같은 전용 호출
  문법은 공통 본문에 넣지 않는다.
- Codex UI 메타데이터는 `agents/openai.yaml`에서 관리한다. `default_prompt`에는 정확한 `$skill-name`을 넣고,
  `short_description`은 25~64자로 유지한다.
- 기존 스킬을 업데이트할 때는 중복 기능을 만들지 말고 기존 절차·스크립트·참조를 확장한다.

## 권한·명령 규칙·훅

- `manifest.json`의 권한 확대는 최소 범위의 정확한 명령 prefix만 허용한다. `bash`, `sh`, `python3`, `curl`,
  `git`, `rm`처럼 광범위한 실행을 통째로 허용하지 않는다.
- Claude allow 항목과 Codex rule은 표현 방식이 다르므로 한쪽 문자열을 다른 쪽에 그대로 복사하지 않는다.
  양쪽에서 실제로 필요한 최소 동작만 각각 선언한다.
- `.env`, `*.session`, `mariadb_data/`, `ollama_data/` 보호와 민감 거래 로직 가드는 제거하거나 완화하지 않는다.
- `guard_sensitive`, `quality_after_edit`, `deploy_on_stop`을 끄거나 동작 범위를 넓히기 전에는 사용자 확인을 받는다.
- Stop 훅은 빌드와 PM2 재시작을 일으킬 수 있다. 훅 변경 검증은 빈 pending 상태나 모의 입력으로 수행하고,
  사용자가 요청하지 않은 실제 배포·재시작으로 시험하지 않는다.
- Claude와 Codex의 훅 입력·출력 JSON은 서로 다를 수 있다. 훅은 멱등적으로 작성하고, 동시에 실행돼도 안전하게
  원자적 파일 교체를 사용하며, 출력에 비밀값을 포함하지 않는다.

## 변경 및 검증 순서

1. 관련 공통 원본만 수정한다.
2. `python3 .agent-config/sync.py`로 양쪽 생성물을 갱신한다.
3. `python3 .agent-config/sync.py --check`가 드리프트 없이 통과하는지 확인한다.
4. 스킬 변경은 공통 원본과 `.agents/skills/` 양쪽에 `quick_validate.py`를 실행한다.
5. Python 훅·생성기 변경은 `py_compile`, 셸 훅 변경은 `bash -n`, JSON/TOML·Codex rule 변경은 각 파서로
   검증한다.
6. 훅 정의가 바뀌면 새 세션에서 다시 로드하고 Codex `/hooks`에서 변경된 훅을 검토·승인한다.
7. 완료 보고에는 권한 확대 여부, 훅/배포 영향, 동기화·검증 결과를 명시한다.
