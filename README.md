# Jongalab

Jongalab 은 실시간 한국 주식 분석 플랫폼입니다.
유튜브·텔레그램·뉴스 같은 콘텐츠를 LLM 으로 분석하고, 수급과 기술적 지표로 종목을 점수화해
**매일 아침 리포트**와 **매매 시그널**을 만들어 줍니다.

분석가가 여러 채널을 직접 모니터링하며 종목을 추려내던 과정을 자동화하는 것이 목표입니다.
콘텐츠 수집부터 분석, 종목 스크리닝, 종가베팅 전략 실행, 대시보드 시각화까지 하나의 파이프라인으로 이어집니다.

> 작업 규칙·가드레일·검증 절차 등 기여자 가이드는 [`AGENTS.md`](AGENTS.md) 에 정리되어 있습니다.

---

## 무엇을 하나요

- **콘텐츠 수집과 분석** — 주식 관련 유튜브 채널, 텔레그램 방, 뉴스를 자동으로 수집하고
  LLM 으로 어떤 종목을 어떤 맥락으로 언급했는지 분석합니다.
- **수급·기술적 스크리닝** — 기관·외국인·개인·프로그램 매매 등 수급 데이터와 시세를 바탕으로
  종목을 점수화해 순위를 매깁니다.
- **일일 리포트** — 매일 장 시작 전, 분석 결과를 종합한 리포트와 관심 종목 Top 리스트를 만듭니다.
- **갭·종가베팅** — 리포트로 추린 종목의 시초가 갭과 장중 흐름을 추적하고,
  종가베팅 전략에 따라 매매 시그널을 산출합니다.
- **대시보드** — 리포트, 종목 상세, 수급, 테마, 뉴스, 콘텐츠 피드를 모바일 우선 웹 화면으로 보여 줍니다.
- **자동매매 집행** — 매수 신호를 받아 종가에 주문을 내고, 다음 날 아침 시초가에 청산합니다.
  시장 상황에 따라 투입 금액을 줄이는 게이트와 손절·트레일링 스탑이 붙어 있습니다.

---

## 어떻게 구성되어 있나요

크게 세 개의 앱으로 나뉩니다. 같은 MariaDB 서버를 쓰되 데이터베이스(스키마)는 분리합니다.

- **`jongalab/` — 메인 앱**
  분석·스크리닝·매수신호·대시보드를 담당합니다.
  Python(FastAPI) 백엔드(`:8000`)와 Next.js 프론트엔드(`:3000`)로 이루어져 있고,
  콘텐츠 수집·뉴스·공시·리포트 같은 저위험 작업은 통합 스케줄러가, 갭 체크·종가베팅처럼
  시각에 민감한 작업은 PM2 cron 이 주기 실행합니다.

- **`trading/` — 자동매매 집행 서버**
  메인 앱이 만든 매수 신호를 받아 **실제 주문을 집행하고 포지션·리스크를 관리**합니다(`:8002`,
  자체 대시보드 `:3001`). 주문 권한은 이 앱만 가지며, 시드 배분·감액 게이트·손절/청산이 여기 있습니다.

- **`kiwoom/` — 키움 데이터 서버**
  키움증권 REST API 에서 시세·수급·차트·테마 데이터를 조회하는 전용 서버(`:8001`)입니다.
  메인 앱은 키움을 직접 부르지 않고 이 서버를 통해서만 데이터를 받아 갑니다.
  **데이터 조회 전용**이라 주문·계좌 기능은 노출하지 않습니다.

LLM 은 용도에 따라 나눠 씁니다. 콘텐츠 분석은 로컬 Ollama 로, 일일 다이제스트는 OpenAI 로 처리합니다.

---

## 기술 스택

- **백엔드** — Python 3.12+, FastAPI, `uv`
- **데이터/분석** — yfinance, telethon, youtube-transcript-api, feedparser
- **LLM** — Ollama(로컬), OpenAI
- **프론트엔드** — Next.js 16, React 19, Tailwind 4, recharts (모바일 우선)
- **인프라** — MariaDB, Ollama, PM2

---

## 시작하기

1. **인프라 기동** (MariaDB + Ollama)
   ```bash
   docker compose up -d
   ```
2. **DB 스키마 생성** — 각 앱의 `sql/` 안에서 `1. create_database.sql` → `2. create_table.sql` 순서로 실행합니다.
3. **환경 변수 설정** — 루트의 `.env` 단일 파일을 양쪽 앱이 함께 로드합니다.
   DB 접속 정보는 공유하고, 데이터베이스 이름만 `JONGALAB_DB_NAME` / `KIWOOM_DB_NAME` 으로 나눠 줍니다.
   LLM 키, 텔레그램·키움 자격증명 등도 여기에 둡니다.

> `.env`, `*.session`, `mariadb_data/`, `ollama_data/` 는 커밋·수정하지 않습니다.

---

## 실행하기

개발 중에는 개별로 띄웁니다. (Python 명령은 각 서브프로젝트 디렉터리 기준입니다.)

```bash
# 메인 API (:8000)
uv run --directory jongalab uvicorn api:app --host 127.0.0.1 --port 8000

# 자동매매 API (:8002)
uv run --directory trading uvicorn api:app --host 127.0.0.1 --port 8002

# 키움 데이터 API (:8001)
uv run --directory kiwoom uvicorn api:app --host 127.0.0.1 --port 8001

# 프론트엔드 (:3000 / 자동매매 대시보드 :3001)
cd jongalab/frontend && npm run dev
cd trading/frontend && npm run dev
```

운영 환경에서는 PM2 로 일괄 관리합니다. API·웹·키움 서버·텔레그램 수집·통합 스케줄러는 상시
실행되고, 토큰 갱신·갭 체크·종가베팅·매수/청산 워커는 cron 스케줄로 돕니다.

```bash
pm2 start ecosystem.config.js
pm2 status
pm2 logs
```

---

## 검증

자동화 테스트가 없어 "직접 띄워서 확인"하는 방식을 따릅니다. 변경 후 다음을 수행합니다.

```bash
# 프론트(.ts/.tsx) 변경 시
cd jongalab/frontend && npx tsc --noEmit && npm run lint

# Python(.py) 변경 시 — 바뀐 파일마다
uv run --directory <jongalab|kiwoom> python -m py_compile <파일경로>
```

자금 경로(`trading/`)를 건드렸다면 단위 테스트도 함께 돌립니다.

```bash
uv run --directory trading --group dev pytest
```

자세한 검증 규칙과 가드레일은 [`AGENTS.md`](AGENTS.md) 를 참고하세요.

---

## 문서 구성

| 위치 | 내용 |
|---|---|
| `jongalab/README.md` · `trading/README.md` · `kiwoom/README.md` | 각 앱의 **현재 구조와 상태** |
| [`docs/history/`](docs/history/) | 판정·변경 **이력**(백테스트 수치·기각 근거·사고 경위, 축별 6개) |
| [`docs/plan/`](docs/plan/) | 설계 문서 |
| [`AGENTS.md`](AGENTS.md) | 작업 규칙·가드레일·검증 절차 |
