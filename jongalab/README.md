# jongalab — 메인 앱 (분석 · 스크리닝 · 매수신호 · 대시보드)

콘텐츠(유튜브/텔레그램/뉴스)를 LLM 으로 분석하고, 수급·기술적 지표로 종목을 점수화해
**일일 리포트**와 **종가베팅 매수 신호**를 만든다. FastAPI 백엔드(`:8000`) + Next.js
프론트(`:3000`) + PM2 cron 워커로 구성된다. 시세·수급 데이터는 직접 키움을 부르지 않고
`kiwoom/` 데이터 서버(`:8001`)를 HTTP 로 호출해 받는다.

> 이 README 는 **주요 로직과 코드 구조의 소스 오브 트루스**다.
> `core/`·`routers/`·`workers/` 의 주요 로직을 바꾸면 **이 파일도 함께 갱신**한다(아래 "유지보수" 참고).
> 작업 규칙·가드레일·검증 절차는 루트 [`AGENTS.md`](../AGENTS.md) 를 따른다.

---

## 코드 구조

```
jongalab/
├── api.py            # FastAPI 진입점 — 라우터 등록(include_router)
├── core/             # 비즈니스 로직 + 데이터 접근(repository)
├── routers/          # HTTP 엔드포인트 핸들러
├── workers/          # PM2 cron 백그라운드 잡
├── sql/              # jongalab DB 스키마 (1.create_database → 2.create_table)
└── frontend/         # Next.js 대시보드 (frontend/README.md 참고)
```

### `core/` — 비즈니스 로직
| 파일 | 책임 |
|---|---|
| `config.py` | `.env` 로딩, DB(jongalab/trading)·AI(Ollama/OpenAI)·키움/KIS 설정 |
| `db.py` | 컨텍스트 매니저(`get_db`, `get_trading_db`) — 안전한 연결 관리 |
| `ai_service.py` | **LLM 추상화(`analyze_content`)** — Ollama(콘텐츠 분석)/OpenAI(다이제스트) 분기. 직접 SDK 호출 금지, 항상 여기로 |
| `ai_utils.py` | LLM 응답 파싱(JSON 추출, 코드펜스/`<think>` 제거) |
| `trading_engine.py` | **종가베팅 분석 엔진** ⚠️민감/가드. Phase 1 사전 스크리닝(수급·정배열·거래대금) → Phase 2 정밀(수급 그레이드·신고가·대장주·테마·콘텐츠) → 종합점수·top-N |
| `prompts.py` | 콘텐츠 분석 프롬프트 ⚠️민감/가드 (sentiment_score, related_companies 등) |
| `kiwoom_client.py` | 키움 데이터 서버(`:8001`) HTTP 클라이언트 — 기본/상세/수급/차트/주도주 |
| `kis_client.py` | 한국투자증권(KIS) Open API — 코스피200 야간선물 시세, WebSocket 키 |
| `market_data.py` | 통합 시세 조회(국내→키움, 선물→KIS, 지수/원자재/환율→yfinance) |
| `sector_resolver.py` | 티커→섹터 해석(ticker_dictionary 캐시, TTL 1년) |
| `ticker.py` | 기업명↔티커 변환, 신규 티커 등록, 콘텐츠 본문 기업명 추출 |
| `news_matcher.py` | 뉴스 헤드라인 → 종목 사전매칭(LLM 없음). ticker_dictionary(ACTIVE) 인메모리 매처, 경계 룩어라운드로 오탐 억제 |
| `news_summary.py` | 후보 소수 뉴스 재료 배치 요약(Ollama, `analyze_content` 경유). 프롬프트는 가드 파일과 분리 |
| `filters.py` | 분석 결과 저장 여부 판단(점수 범위·티커 포함·환각 검증) |
| `backtest.py` | 가중치 제안 백테스트 — `score_candidate` 공식을 미러링(`recompute_score`)해 저장된 표본에 제안 가중치를 재적용, 승자/패자 판별력 비교. ⚠️엔진 공식 변경 시 미러도 갱신(테스트가 드리프트 감지) |
| `notifications.py` | 텔레그램 알림(재시도 포함) |
| `market_calendar.py` | KRX 개장일 판별(exchange_calendars XKRX) |
| `logging_setup.py` | 로그 설정 |

#### `core/repository/` — DB 접근 계층 (raw SQL 은 반드시 여기서만)
`content`(콘텐츠 분석) · `news`(뉴스 속보 언급 `news_mention`) · `source`(채널) · `ticker`(기업명↔티커, 상장종목 벌크 시딩) · `stock_report`(종목일간리포트) ·
`sector_report`(주도 섹터) · `trade_signal`(→ trading DB 매수신호 핸드오프, 멱등 upsert) ·
`trade_result`(trading.audit_log 실현손익 읽기) · `strategy_config`(점수 가중치·임계값) ·
`weight_tuning`(주간 GPT 제안) · `kis_token` · `kis_night_future` · `telegram_user`.

### `routers/` — 엔드포인트
`admin`(인증) · `contents`(콘텐츠) · `news`(뉴스 재료 히트 `/api/news/heat`) · `market`(주가/지수) · `stock_report`(리포트·갭) ·
`source`·`strategy_config`·`weight_tuning`·`telegram_user`(admin 전용) · `ticker`(조회 공개/수정 admin).
새 라우터는 `routers/` 에 만들고 `api.py` 의 `include_router` 로 등록한다.

### `workers/` — PM2 cron (스케줄은 루트 `ecosystem.config.js`)
| 워커 | 스케줄 | 역할 |
|---|---|---|
| `youtube_collector` | 15분 | 채널 RSS → 자막 → Ollama 분석 → `content_analysis` |
| `telegram_listener` | 상시 | Telethon 감시. **일반 채널**(platform=telegram)→ LLM 분석 → `content_analysis`. **뉴스 채널**(platform=news, 고빈도)→ LLM 없이 사전매칭 → `news_mention` |
| `news_ticker_seed` | 일 07:30 (등록 시 1회) | 키움 ka10099(코스피/코스닥) → `ticker_dictionary` ACTIVE 업서트. 뉴스 사전매칭 커버리지용 |
| `cleanup_content` | 매일 04:00 | `content_analysis` 3개월 + `news_mention` 14일 이전 행 삭제(테이블 비대화 방지) |
| `closing_bet` | 평일 08:30~20시(30분) | Phase 1/2 스크리닝 → `daily_stock_report` + `trade_signal` 적재 |
| `gap_check` (`--retry`) | 평일 08:05 / 09:05 | 전날 top-10 현재가 → 갭 등락률 → ADMIN 알림 |
| `weight_tuner` | 토 08:00 | 지난주 실현손익 → GPT 가중치 제안(`weight_tuning_proposal`) |
| `kis_night_futures_ws` | 평일 18:00~익일 새벽 | KIS WebSocket 야간선물 체결 → `kis_night_future` |
| (토큰) `kis_token_refresh` | 매일 07:00 | 키움+KIS 토큰 갱신(`refresh_tokens.sh`) |

---

## 핵심 도메인 흐름

```
콘텐츠 수집(youtube/telegram) ──► content_analysis (sentiment, 관련 종목)
뉴스 속보 채널(고빈도) ──사전매칭(LLM X)──► news_mention (종목·헤드라인)
                                        │
종가 분석(closing_bet, 평일 13:00~15:00)│
  Phase 1 거래대금·시총·정배열 필터 ─────┘
  Phase 2 수급(기관/외인/개인/프로그램)+신고가+대장주+테마+콘텐츠+뉴스 점수
  종합점수 = 수급 + 정배열 + 신고가 + 대장주 + 테마 + 콘텐츠 + 뉴스(가중치 튜닝 대상)
        │  · 뉴스 재료: news_count 집계 + 후보 소수 배치 LLM 요약 → daily_stock_report 표시
        │    (SCORE_NEWS_BONUS 기본 0 → 현재 점수 무영향, 주간 튜너가 성과 따라 상향 가능)
        ├─► daily_stock_report (score, rank_no, news_count/summary)  ─► 대시보드/갭체크
        └─► trade_signal (status=pending)        ─► trading 도메인이 집행
다음날 아침 gap_check ─► daily_stock_report.gap_* 갱신
주말 weight_tuner ─► 실현손익 + 지표(콘텐츠·뉴스 포함) 피드백 ─► 가중치 제안
  └► 0 근처 가중치는 절대스텝 부트스트랩 클램프로 성장 가능(±15% 곱셈식이 0을 0에 고정하는 문제 해소)
  └► 관리자 승인 화면에서 백테스트 검증(제안 가중치 재적용, core/backtest.py) 확인 → 승인 시 strategy_config 반영
```

**경계**: jongalab 은 **무엇을 살지** 결정해 `trade_signal` 에 적재만 한다.
**언제·얼마나·어떻게** 집행하는지는 `trading/` 도메인 책임이다.

---

## 유지보수 (주요 로직 변경 시)
1. 다음 5가지를 먼저 검토: ① 이 기능이 꼭 필요한가 ② 관련 기존 코드가 있는가
   ③ 가장 단순한 구조는 ④ 사용자가 가장 덜 헷갈리는 흐름은 ⑤ 어느 쪽이 더 유지보수하기 쉬운가.
2. 구현 전 이 README 의 해당 섹션을 읽어 구조를 파악한다.
3. 구현 후 바뀐 책임/흐름을 이 README 에 반영한다.
4. DB 접근은 `core/repository/*`, LLM 은 `core/ai_service.analyze_content` 만 사용한다.
5. 검증: Python 변경마다 `uv run --directory jongalab python -m py_compile <file>`,
   라우터/응답 변경 시 API 기동 후 `curl` 로 status·shape 확인.
6. 순수 로직(예: `core/backtest.py`) 단위 테스트: `uv run --directory jongalab --group dev pytest`
   (DB/네트워크 없이). `recompute_score` 는 실제 `score_candidate` 와 교차검증되므로 엔진 공식 변경 시 함께 갱신.
