# Stock Agent — 에이전트 작업 가이드

> 이 파일은 **모든 AI 코딩 에이전트의 단일 소스(single source of truth)**다.
> Codex 는 `AGENTS.md` 를, Claude Code 는 `CLAUDE.md`(→ 이 파일을 import)를 읽는다.
> 규칙을 바꿀 땐 **이 파일만** 수정한다.

실시간 한국 주식 분석 플랫폼. 콘텐츠(유튜브/텔레그램/뉴스)를 LLM으로 분석하고,
수급·기술적 스크리닝으로 종목을 점수화해 일일 리포트와 매매 시그널을 만든다.
**Python 백엔드(분석/트레이딩/워커) + Next.js 프론트(대시보드)** 하이브리드.

## 디렉터리 구조
루트는 **`jongalab/`(메인 앱)** 과 **`kiwoom/`(키움 데이터 전용 서버)** 로 분리된다.
공통 인프라는 각자 최소 복제하고, **같은 MariaDB 서버에 DB(스키마)를 분리**해 쓴다 —
jongalab 은 `jongalab` DB(분석/리포트/소스 등), kiwoom 은 전용 `kiwoom` DB(`kiwoom_token`).
DB명은 `.env` 의 `JONGALAB_DB_NAME`/`KIWOOM_DB_NAME` 로 각각 주입한다(`DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_PORT` 는 공유).

### `jongalab/` — 메인 앱 (분석/트레이딩/워커/프론트)
- `core/` — 비즈니스 로직. `ai_service.py`(LLM 추상화), `trading_engine.py`(종가베팅 전략),
  `db.py`, `config.py`, `kiwoom_client.py`(키움 데이터 서버 HTTP 클라이언트), `repository/`(DB 접근 계층, 패턴 준수 필수)
- `routers/` — FastAPI 라우트 핸들러 (`api.py`의 `app`에 등록)
- `workers/` — PM2 cron 백그라운드 잡 (daily_digest, youtube_collector, telegram_listener,
  gap_check, closing_bet)
- `frontend/` — Next.js 16 App Router + Tailwind 4 + recharts. `app/`(페이지), `components/`,
  `lib/api.ts`(fetch 래퍼, API_BASE=:8000), `types/index.ts`
- `sql/` — `jongalab` DB 스키마 (`1. create_database.sql` + `2. create_table.sql`)

### `kiwoom/` — 키움 데이터 전용 서버 (FastAPI, :8001)
- `core/kiwoom_api.py`(키움 REST 클라이언트), `core/repository/kiwoom_token.py`(토큰 저장),
  `core/{config,db,logging_setup}.py`(DB 키만 가진 최소 복제)
- `api.py` — 데이터 조회 엔드포인트(소비자가 쓰는 11종) + `/health`
- `workers/kiwoom_token_refresh.py` — 매일 07:00 토큰 갱신 (cron)
- `sql/` — `kiwoom` DB 스키마 (`1. create_database.sql` + `2. create_table.sql`, `kiwoom_token`)
- **데이터 조회 전용**: 주문/계좌는 노출하지 않는다. jongalab 은 `core.kiwoom_client.KiwoomRestClient`
  로 `http://127.0.0.1:8001` 호출(`KIWOOM_BASE_URL`).

### 루트
- `ecosystem.config.js`, `.env`(단일, 양쪽이 절대경로로 로드), `.claude/`

## 명령어
> 파이썬 명령은 해당 서브프로젝트 디렉터리(`jongalab/` 또는 `kiwoom/`)에서 실행한다.
| 목적 | 명령 |
|---|---|
| jongalab API 기동 | `uv run --directory jongalab uvicorn api:app --host 127.0.0.1 --port 8000` |
| kiwoom API 기동 | `uv run --directory kiwoom uvicorn api:app --host 127.0.0.1 --port 8001` |
| 워커 단발 실행 | `uv run --directory jongalab workers/<name>.py` |
| 프론트 dev | `cd jongalab/frontend && npm run dev` (`:3000`) |
| 프론트 검증 | `cd jongalab/frontend && npx tsc --noEmit && npm run lint` |
| Python 문법 검증 | `uv run --directory <jongalab\|kiwoom> python -m py_compile <relpath>` |
| 전체 운영 | `pm2 start ecosystem.config.js` / `pm2 logs` / `pm2 status` |
| DB 콘솔 | `docker exec -it <mariadb 컨테이너> mysql -u<user> -p<pw> <db>` |

## 아키텍처 규칙
- **DB 접근은 반드시 `core/repository/*` 패턴을 따른다.** 라우터/워커에서 raw SQL 직접 작성 금지.
- **LLM 호출은 `core/ai_service.analyze_content()` 추상화를 사용한다.** Ollama(로컬, 콘텐츠 분석)와
  OpenAI(일일 다이제스트)를 그 안에서 분기한다. 직접 SDK 호출 추가 금지.
- 새 라우터는 `routers/`에 만들고 `api.py`에 `include_router` 등록.
- 도메인 용어 유지: 수급(기관/외국인/개인/프로그램), 테마, 갭, 종가베팅, rank_no.

## 프론트엔드 규칙
- **모바일 우선(mobile-first)**. 이 대시보드는 모바일에서 자주 쓰인다. 모든 UI는 작은 화면을
  먼저 만족시키고 `sm:`/`md:`로 확장한다. 데스크탑만 보고 끝내지 말 것.
- 차트는 recharts, 아이콘은 lucide-react, 스타일은 Tailwind 4 유틸리티.
- 타입은 `types/index.ts`에 정의하고 백엔드 응답 shape과 일치시킨다.

## ⚠️ 절대 규칙 (가드레일)
- `jongalab/core/trading_engine.py`, `jongalab/core/prompts.py`는 **민감 로직 파일**이다(가드 훅이 편집 차단).
  변경은 복구 불가하고 팀에 공유되지 않는다. 수정 전 반드시 사용자 확인을 받고, 수정 시 변경 내용을 명시한다.
  요청 없는 리팩터링/정리 금지.
- `.env`, `*.session`, `mariadb_data/`, `ollama_data/`는 읽기·수정·커밋 금지.
- 비밀키/토큰을 코드나 로그에 하드코딩하지 않는다. 모두 `.env` → `core/config.py` 경유.

## 검증 (테스트 없음 — 모든 에이전트 공통)
자동화 테스트가 없으므로 "띄워서 확인"이 표준이다. 작업 완료 전 **반드시** 수행한다:
1. 프론트(`.ts/.tsx`) 변경 → `cd frontend && npx tsc --noEmit && npm run lint`
2. Python(`.py`) 변경 → 바뀐 파일마다 `uv run python -m py_compile <file>`
3. 라우터/응답 변경 → API 기동 후 `curl`로 엔드포인트 status·shape 확인
4. UI 변경 → `:3000` 라우트 200 + **모바일 레이아웃** 우선 점검

실패가 있으면 수정 후 다시 통과시킨 뒤에만 완료로 보고한다. 추측 금지 — 실행 결과로 보고한다.

## 도구별 하네스 메모
- **Claude Code**: `.claude/` 에 자동화 레이어가 있다 — 편집 후 위 검증을 자동 실행하는 훅,
  민감 파일 편집 차단 훅, 슬래시 커맨드(`/check` `/run-api` `/run-web` `/db` `/new-card` `/new-worker`),
  전문 서브에이전트(backend/frontend/verify). 위 "검증" 단계가 훅으로 강제된다.
- **Claude Code 자동 배포 훅**: 코드 변경은 턴 종료(Stop) 시점에 PM2 에 자동 반영된다
  (`.claude/hooks/track-changes.sh` 가 변경 파일을 누적 → `deploy-on-stop.sh` 가 분류·실행).
  - `jongalab/frontend/**` 변경 → `npm run build` 후 `jongalab-fe` 재시작(빌드 실패 시 Stop 을 막아 이어서 고치게 함).
    또한 프론트 편집마다 **모바일 최우선** 가이드가 컨텍스트로 주입된다.
  - `jongalab/api.py`/`jongalab/routers/**`/`jongalab/core/**` → `jongalab-be` 재시작,
    `jongalab/core/**`·`telegram_listener.py` → `jongalab-telegram` 재시작.
  - `kiwoom/api.py`/`kiwoom/core/**` → `kiwoom-api` 재시작.
  - cron 워커(`youtube_collector`/`daily_digest`/`gap_check`/`closing_bet`/`kiwoom_token_refresh`)는
    **재시작하지 않는다** — cron 마다 새 프로세스로 spawn 되어 다음 스케줄 실행 때 자동 반영된다.
  - 해당 PM2 앱이 `online` 이 아니거나 pm2 가 없으면 조용히 건너뛴다.
- **Codex** (및 기타): 위 자동화가 없으므로 **검증 단계를 직접 실행**해야 한다. 가드레일(민감 파일,
  비밀키)도 사람이 지키듯 스스로 지킨다. 설정은 글로벌 `~/.codex/config.toml`,
  승인/샌드박스는 실행 플래그로 조절한다.
