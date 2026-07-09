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
| `ai_service.py` | **LLM 추상화(`analyze_content`)** — Ollama(콘텐츠 분석)/OpenAI(다이제스트) 분기. 직접 SDK 호출 금지, 항상 여기로. LLM 은 구조화 JSON(tldr/tags/summary/stocks/strategy)만 내보내고 `build_analysis_markdown()` 이 `analysis_content`(마크다운)를 재조립 |
| `ai_utils.py` | LLM 응답 파싱(JSON 추출, 코드펜스/`<think>` 제거) |
| `trading_engine.py` | **종가베팅 분석 엔진** ⚠️민감/가드. Phase 1 사전 스크리닝(거래대금 상위 50·시총) → Phase 2 정밀(수급 그레이드·정배열/신고가·대장주·테마·콘텐츠·등락률) → 종합점수·top-N. 2026-07-03 실증 반영: 등락률 항(2~12% 가점/15%+ 감점) 신설, 대장주 10→3·프로그램 10→0 축소, ka10131 연속수급 버그(_AL 접미사·코스피만·abs) 수정. 2026-07-07: 거래대금 후보 풀 30→50 확대, 테마 보너스는 거래대금 상위 50 교집합에만 부여. 2026-07-06: 5일 수급점수에서 기관/외인 순매수 0(ka10059 잠정치 미반영 가능성)을 중립 처리 — 가점 없이 스트릭 유지, 순매도(<0)만 스트릭 리셋(당일 집계 지연이 연속매수 보너스를 무너뜨리던 문제 수정) |
| `prompts.py` | 콘텐츠 분석 프롬프트 ⚠️민감/가드. 구조화 출력(sentiment_score·tldr·tags·summary·stocks[방향/확신/시간축]·strategy·related_companies) |
| `kiwoom_client.py` | 키움 데이터 서버(`:8001`) HTTP 클라이언트 — 기본/상세/수급/차트/주도주 |
| `kis_client.py` | 한국투자증권(KIS) Open API — 코스피200 야간선물 시세, WebSocket 키 |
| `market_data.py` | 통합 시세 조회(국내→키움, 선물→KIS, 지수/원자재/환율→yfinance). `fetch_edge_market_snapshot()` 은 표시용 경로를 재사용해 시장 스냅샷 1행(코스피/코스닥·NQ·SPX·SOX·VIX·환율·K200 주야간선물)을 조립 |
| `sector_resolver.py` | 티커→섹터 해석(ticker_dictionary 캐시, TTL 1년) |
| `ticker.py` | 기업명↔티커 변환, 신규 티커 등록, 콘텐츠 본문 기업명 추출 |
| `news_matcher.py` | 뉴스 헤드라인 → 종목 사전매칭(LLM 없음). ticker_dictionary(ACTIVE) 인메모리 매처, 경계 룩어라운드 + 발행처 대괄호([]·【】) 제거로 오탐 억제 |
| `news_summary.py` | 후보 소수 뉴스 재료 배치 요약(Ollama, `analyze_content` 경유). 요약과 함께 재료 방향(`news_sentiment` 0~100)·유형(`news_catalyst`, 화이트리스트 강제)을 같은 1회 호출로 라벨링. 프롬프트는 가드 파일과 분리 |
| `filters.py` | 분석 결과 저장 여부 판단(점수 범위·티커 포함·환각 검증) |
| `backtest.py` | 가중치 제안 백테스트 — `score_candidate` 공식을 미러링(`recompute_score`)해 저장된 표본에 제안 가중치를 재적용, 승자/패자 판별력 비교. ⚠️엔진 공식 변경 시 미러도 갱신(테스트가 드리프트 감지) |
| `edge_predicate.py` | **Edge Ledger predicate 평가기**(순수 함수, DB 무의존). `evaluate(predicate, row, market)` — 조건 목록 AND 결합(op 9종: == != > >= < <= between in not_null, `market.` 접두사로 market_snapshot 참조, NULL=매칭실패). `validate_predicate` 로 저장 전 검증. 단위 테스트 `tests/test_edge_predicate.py` 가 계약 고정 |
| `edge_selection.py` | **선정 레이어**(순수 함수). `select_signals(mode, candidates, live_rules, veto_rules, top_n, market)` — `EDGE_SELECTION_MODE`(legacy/hybrid/rules)별 selected 판정 + veto(reduce-only, 전 모드) + rule_names 귀속. 점수·rank_no·저장은 불변. 단위 테스트 `tests/test_edge_selection.py` |
| `edge_policy.py` | **Edge Ledger 정책 단일 소스**(순수 함수). ① rule 역할 판정(`rule_role`: 명시 `role` 컬럼(selector/veto/benchmark) 우선, 구 스키마는 family 겸용 매핑 폴백 — closing_bet 선정·라우터 검증이 공유. `ROLES`/`FAMILIES`(도메인 7종) 레지스트리. 2026-07-09 sql/15 로 role·family 분리: 수급 밴드 4종은 role=benchmark(측정 도구가 실탄 승격되는 경로 차단), veto 는 도메인 family+role=veto) ② 선정 시점 실행 가능성(`selection_executable` — 19:50/익일 수집 피처를 쓰는 rule 은 선정 때 NULL→무음 no-op 라 live 부적격) ③ 승격 게이트(`check_promotion`: n·거래일 수(`n_days`≥`PROMO_MIN_DAYS`=10, 종목-일 클러스터링 과신 방지)·ci_low·**live 대조군 우위**(부재 시 fail-closed)·실행 가능성 — 라우터 409 사유·평가기 알림·`stats.promo_eligible` 이 전부 이 함수에서 파생). 단위 테스트 `tests/test_edge_policy.py` |
| `edge_features.py` | **F5 수급 구조 피처 파생**(순수 함수, DB 무의존). `afternoon_ret`(당일 13시 시간봉 시가→현재가 %)·`prog_buy_days`(최근 5일 중 프로그램 순매수일)·`vol_ratio`(당일 거래량÷20일 평균) — closing_bet 이 이미 수집한 응답에서 스칼라를 굽는다. 결측=None(predicate 의 NULL=매칭실패 계약과 맞물림). 단위 테스트 `tests/test_edge_features.py` |
| `daily_ohlc.py` | 수정주가 일봉(ka10081)·분봉(ka10080) 파싱 + 결과 라벨 아티팩트 가드(`SANE_RET_PCT`=±35%) **공유 모듈** — outcome_backfill(일봉·실집행 레그)·gap_check --label-nxt 가 함께 사용(라벨 간 유효성 기준이 어긋나면 청산창 비교가 오염되므로 라벨 경로는 반드시 이 모듈만) |
| `notifications.py` | 텔레그램 알림(재시도 포함) |
| `market_calendar.py` | KRX 개장일 판별(exchange_calendars XKRX) |
| `logging_setup.py` | 로그 설정 |

#### `core/repository/` — DB 접근 계층 (raw SQL 은 반드시 여기서만)
`content`(콘텐츠 분석) · `news`(뉴스 속보 언급 `news_mention`) · `source`(채널) · `ticker`(기업명↔티커, 상장종목 벌크 시딩) · `stock_report`(종목일간리포트 — 리포트 저장·갭 체크·NXT 스냅샷·결과 백필) ·
`sector_report`(주도 섹터) · `market_snapshot`(일 단위 시장 피처 — 지수·선물·VIX·환율, F2·레짐 연구용) · `trade_signal`(→ trading DB 매수신호 핸드오프, 멱등 upsert) ·
`trade_result`(trading.audit_log 실현손익 읽기) · `strategy_config`(점수 가중치·임계값) ·
`weight_tuning`(주간 GPT 제안) · `edge_rule`(가설 원장 CRUD·stats·일별 채점 edge_rule_daily) · `kis_token` · `kis_night_future` · `telegram_user`.

### `routers/` — 엔드포인트
`admin`(인증) · `contents`(콘텐츠) · `news`(뉴스 재료 히트 `/api/news/heat`) · `market`(주가/지수) · `stock_report`(리포트·갭) ·
`source`·`strategy_config`·`weight_tuning`·`telegram_user`(admin 전용) · `ticker`(조회 공개/수정 admin) ·
`edge_rule`(가설 원장 — GET 스코어보드 공개(daily 는 matched 제외 스칼라만+최신 매칭 1일치 별도, `/{id}/matched?days=`(≤90)로 날짜별 매칭 종목 이력을 별도 제공 — 종목별 change_pct·selected 를 리포트에서 조인해 복기 맥락 포함), POST 등록/승격/강등만 admin. 등록 시 `title`(한글 카드 제목)·`description`(인과 근거) 필수, `family`(도메인)·`role`(selector/veto/benchmark, 기본 selector)은 edge_policy 레지스트리로 검증 — 같은 family 가설이 늘며 카드 구분이 안 되던 문제로 2026-07-06 title 컬럼 추가(NULL 이면 프론트가 name 슬러그 폴백). 승격 게이트는 `core/edge_policy.check_promotion` 단일 소스 — 미충족 시 409+사유, force 없음, 대조군 부재 시 fail-closed. 라우터는 월 승격 상한(2개)만 추가 검사).
새 라우터는 `routers/` 에 만들고 `api.py` 의 `include_router` 로 등록한다.

### `workers/` — PM2 cron (스케줄은 루트 `ecosystem.config.js`)
| 워커 | 스케줄 | 역할 |
|---|---|---|
| `youtube_collector` | 15분 | 채널 RSS → 자막 → Ollama 분석 → `content_analysis` |
| `telegram_listener` | 상시 | Telethon 감시. **일반 채널**(platform=telegram)→ LLM 분석 → `content_analysis`. **뉴스 채널**(platform=news, 고빈도)→ LLM 없이 사전매칭 → `news_mention` |
| `news_ticker_seed` | 일 07:30 (등록 시 1회) | 키움 ka10099(코스피/코스닥) → `ticker_dictionary` ACTIVE 업서트. 뉴스 사전매칭 커버리지용 |
| `cleanup_content` | 매일 04:00 | `content_analysis` 3개월 + `news_mention` 14일 이전 행 삭제(테이블 비대화 방지) |
| `closing_bet` | 평일 08:30~20시(30분) | Phase 1/2 스크리닝 → `daily_stock_report`(Phase 2 **유니버스 전체** 저장) + `trade_signal`(selected만 핸드오프, `rule_names` 태깅) 적재. 저장은 **분석 컬럼만 upsert**(탈락 종목만 삭제) — 다른 워커가 같은 날 행에 쓴 관측 컬럼(19:50 NXT 스냅샷 등)을 20:00 이후 재실행이 지우지 않는다(2026-07-09, 이전 DELETE+INSERT 는 매일 소실시킴). Phase 2는 음전 후보도 정밀분석·저장해 rule_evaluator 연구 표본으로 쓰고, 실제 selected/핸드오프만 선정 레이어에서 음전 제외한다(2026-07-07). 정배열/신고가는 가점으로만 반영(2026-07-03 풀 확대). **선정 레이어**(`edge_selection`, `EDGE_SELECTION_MODE` 기본 `legacy`=음전 제외 후 점수 top-N)가 `selected`/핸드오프만 정하고 점수·rank_no·저장은 불변 — `hybrid`/`rules` 는 데이터 게이트+승인 후 전환(Phase 4). veto rule 은 전 모드에서 선정 직전 제외 |
| `gap_check` (`--base-krx`/`--base-nxt`/`--check-nxt`/`--label-nxt`/`--check-krx`) | 평일 15:20 / 19:50 / 08:03 / 08:06 / 09:03 | 실매매 청산 창과 동일 기준의 갭 측정. 15:20 KRX(top-10)·19:50 NXT 기준가를 state 로 수집(19:50 NXT 조회되는 종목=NXT 종목) → 익일 08:03 NXT 종목(`gap_nxt_*`), 09:03 KRX 종목(`gap_krx_*`) 확정 — 종목별로 자기 venue 창 하나만 채점. 기준가 미수집 시 리포트가 폴백(알림에 ≈ 표시). 텔레그램 알림은 09:03 확정 후 하루 1회. **19:50(`--base-nxt`)은 확장 관측**: 유니버스 전체에 KRX 확정 종가+NXT 현재가(종목당 2콜)를 붙여 `daily_stock_report` NXT 스냅샷(`krx_close_price`·`nxt_price_1950`·`nxt_gap_pct`·`nxt_after_value`·`nxt_listed`) UPDATE + `market_snapshot` 1행 upsert. **08:06(`--label-nxt`)은 엣지 연구 라벨**: 전일 유니버스 전체 NXT 상장 종목의 08:06 NXT 가격 → `nxt_open_price`·`nxt_open_ret`(앵커=KRX 확정 종가) UPDATE — 실매매 08:03(settle·check-nxt, top-10)과 시각·부하 완전 분리. 관측 확장은 매매 영향 0 |
| `outcome_backfill` | 평일 09:30 | `daily_stock_report` 유니버스 전체에 **일봉 결과 라벨 4종**(`next_open_ret`·`next_high_ret`·`next_low_ret`·`next_close_ret` = 리포트일 종가→다음 거래일 시가/고가/저가/종가 등락률) + **실집행 통합 라벨**(`exec_leg_ret`·`exec_leg_venue`) 백필. `exec_leg_ret` 는 종목별 실제 청산 venue 기준(NXT: 전일 19:50→익일 08:03, KRX: 전일 15:20→익일 09:03)을 하나로 접은 evaluator 기본 라벨. 일봉은 같은 일봉 1회 조회에서 파생, 실집행 레그는 1분봉 첫 체결가 기준. ±35% 초과 아티팩트 스킵, 미완결분은 다음 실행에서 재시도. 실집행 레그는 `exec_leg_ret` 활성 rule 의 가장 이른 registered_at 이후만 대상(활성 rule 이 없으면 **건너뜀** — 과거 전체 분봉 백필 폭주 방지), NXT 시도 후 KRX 폴백 시 로그 기록 |
| `after_hours_labels` | 평일 17:50 | 당일 유니버스 전체에 **시간외 반응 + 리스크 라벨** UPDATE(관측 컬럼 — closing_bet upsert 와 분리, 점수·매매 무영향). ① 시간외단일가 `ah_price`·`ah_flu_rt`·`ah_volume`(ka10087 — 세션 16~18시 **중**에만 값이 살아있어 17:50 스냅샷, 체결 0주는 NULL) + `ah_react`(시간외가 ÷ 당일 KRX 종가 −1%, 앵커=수정주가 일봉 — predicate 가 컬럼 간 비교를 못 해 파생으로 굽는 rule 용 컬럼) — 익일 갭 선행지표 ② 리스크 지표(악재 veto 연구, 전부 **T-1 확정치**라 선정 시점에 알 수 있던 값=누수 없음): `credit_remn_rt`(ka10013 신용 잔고율)·`short_wght`/`_5d`(ka10014 공매도 비중)·`lend_remn`/`lend_irds_5d`(ka20068 대차 잔고·5일 증감 합) ③ `exec_str`/`_5d`(ka10047 체결강도, KRX 마감 후 확정치) ④ `market_snapshot.ah_up3_cnt`/`ah_dn3_cnt`(ka10098 시간외 ±3% 급등/급락 종목 수 — 시장 분위기). 스냅샷 TR 특성상 과거 백필 불가 — 놓친 날은 NULL |
| `rule_evaluator` | 평일 09:40 | **Edge Ledger 일별 채점(2-pass)** — pass1: 활성 rule(status≠retired)을 유니버스 전체 + `market_snapshot` 에 적용(`edge_predicate.evaluate`), `exit_label` 결과 수집 → `mean_net = 평균 − EDGE_COST_PCT` → `edge_rule_daily` upsert(catch-up: 라벨 미도래 날짜는 다음날 재시도, 14일 초과 시 n=0 sentinel 종결 — 실시간 라벨은 소급 불가라 영구 재시도 방지) + registered_at 이후 표본만으로 누적 stats 재계산(`n_days`=라벨 표본이 있는 거래일 수 포함). 채점 당시 미도래였던 `next_low_ret` 는 재시도 마감 전 날짜에 한해 matched 스냅샷에 소급 반영(worst_low_ret 복원 — exec_leg_ret 는 D+1, next_low_ret 는 D+2 에 채워지는 시차 보정). pass2: 전 rule stats 가 신선해진 뒤 `edge_policy.check_promotion`(라우터와 동일 게이트: min_sample + **PROMO_MIN_DAYS=10 거래일** + ci_low>0 + live 대조군 우위 — 종목-일 n 은 같은 날 시장 무브로 상관되어 거래일 수가 실효 표본)으로 `stats.promo_eligible` 저장 + 텔레그램 알림 — 승격 후보(게이트 전체 충족) / 집행 설계 필요(통계·표본 충족이나 선정 시점 실행 불가 피처) / 강등 검토(live, 최근 30표본 mean_net<0). 전이는 관리자 API 수동, 매매 집행 없음 |
| `weight_tuner` | 토 08:00 | 지난주 실현손익(단 `SCORE_LOGIC_MIN_DATE`=2026-07-07 이전 구 로직 주는 스킵) → GPT 가중치 제안 → backtest 검증: IMPROVES=pending(승인 대상) / 그 외=archived(비적용·표시용) + [건강지표] 로깅 |
| `kis_night_futures_ws` | 평일 18:00~익일 새벽 | KIS WebSocket 야간선물 체결 → `kis_night_future` |
| (토큰) `kis_token_refresh` | 매일 07:00 | 키움+KIS 토큰 갱신(`refresh_tokens.sh`) |

---

## 핵심 도메인 흐름

```
콘텐츠 수집(youtube/telegram) ──► content_analysis (sentiment, 한줄요약 tldr, 테마 tags, 종목별 방향 stock_calls)
뉴스 속보 채널(고빈도) ──사전매칭(LLM X)──► news_mention (종목·헤드라인)
                                        │
종가 분석(closing_bet, 평일 13:00~15:00)│
  Phase 1 거래대금(시장별 상위 50) + 관심섹터 보강 · 공통 기본필터(제외키워드·시총·거래대금) ─┘
  Phase 2 음전 포함 정밀분석(연구 표본) → 수급(기관/외인/개인/프로그램)+정배열/신고가+대장주+테마+콘텐츠+뉴스+등락률 점수
  종합점수 = 수급 + 정배열 + 신고가 + 대장주 + 테마(거래대금 상위 50 교집합만) + 콘텐츠 + 뉴스 + 등락률(2~12% 가점 / 15%+ 감점) (가중치 튜닝 대상)
        │  · 뉴스 재료: news_count 집계 + 후보 소수 배치 LLM 요약 → daily_stock_report 표시
        │    (SCORE_NEWS_BONUS 기본 0 → 현재 점수 무영향, 주간 튜너가 성과 따라 상향 가능)
        │  · 뉴스 연구 라벨(2026-07-03~, 점수 무영향 — next_open_ret 조인 엣지 검증용):
        │    집계 — news_unique_count(헤드라인 dedup 고유 기사) · news_pm_count(12시 이후 신선도) ·
        │           news_first_today(14일 내 첫 등장) · news_prior_avg(직전 7일 일평균, 서프라이즈 분모)
        │    LLM — news_sentiment(방향 0~100) · news_catalyst(재료 유형) — 기존 배치 요약 호출에 출력 필드만 추가
        ├─► daily_stock_report — Phase 2 유니버스 전체 저장(selected=1=핸드오프, 0=비선정/음전 연구 후보)
        │     · 기본 조회(대시보드·gap_check)는 selected=1 만; 연구는 include_unselected=True 로 전체
        │     · 저장 시점 파생(API 콜 없음, F4의 눈): sector_rel_ret(등락률−동일섹터 평균)·sector_leader_chg(동일섹터 최고 등락률)
        │     · F5 수급 구조·테마 피처(2026-07-05~, 점수 무영향 — 전부 선정 시점 수집이라 live 자격):
        │       기수집 응답 캡처 — foreign_brokers_buying(ka10002 외국계 창구 2곳+) · prog_buy_days(ka90013 5일 중 순매수일) ·
        │                        afternoon_ret(ka10080 13시 시가→현재가) · theme_strength(ka90001 소속 테마 당일 등락 최대) ·
        │                        frgn_exhaust_rate(ka10001 for_exh_rt)
        │       추가 1콜 — vol_ratio(ka10081 당일 거래량÷20일 평균) / DB 파생 — first_seen(직전 14일 유니버스 부재) ·
        │                  frgn_exhaust_chg(직전 리포트 거래일 대비 소진율 %p, repository.get_prev_frgn_exhaust_map)
        │     · 선정 레이어(edge_selection, EDGE_SELECTION_MODE): 음전 후보는 연구 표본으로 저장하되 핸드오프에서 제외. legacy=점수 top-N(기본) / hybrid=live rule 우선+점수 채움 / rules=live rule 합집합(매칭0=무거래). veto 는 전 모드 선정 직전 제외. live rule 로드 실패 시 모드 자체를 legacy 로 폴백(로그 명시) — 빈 rule 목록으로 rules 를 돌려 무거래가 되는 사고 방지
        └─► trade_signal (status=pending, selected만, rule_names 귀속)  ─► trading 도메인이 집행(도메인 로직 무변경, rule_names 는 안 읽음)
당일 15:20 gap_check --base-krx ─► top-10 KRX 기준가(state) · 다음날 08:03/09:03 --check-* ─► daily_stock_report.gap_*(top-10) 갱신(NXT: 19:50→08:03, KRX: 15:20→09:03)
당일 17:50 after_hours_labels ─► 유니버스 전체 시간외단일가(ah_*, 익일 갭 선행지표) + 리스크 라벨(credit_remn_rt·short_wght/_5d·lend_remn/lend_irds_5d — T-1 확정치, 악재 veto 연구) + 체결강도(exec_str/_5d) UPDATE + market_snapshot 시간외 breadth(ah_up3_cnt/ah_dn3_cnt)
당일 19:50 gap_check --base-nxt ─► top-10 NXT 기준가(state, 갭 체크용) + 유니버스 전체 NXT 스냅샷(daily_stock_report.krx_close_price·nxt_*) + market_snapshot 1행(지수·선물·VIX·환율)
다음날 08:06 gap_check --label-nxt ─► 유니버스 전체 NXT 상장 종목 nxt_open_price·nxt_open_ret(앵커=KRX 확정 종가) — 실매매 08:03 경로와 분리된 청산창 연구 라벨
  └► F1~F4 가설이 볼 수 있는 관측을 15:00 KRX 시점 너머(19:50 애프터마켓·시장 레벨·08:06 프리마켓)로 확장 — 순수 기록 레이어(매매 영향 0)
평일 09:30 outcome_backfill ─► daily_stock_report 일봉 결과 라벨 4종(유니버스 전체, 리포트일 종가→다음 거래일 시가/고가/저가/종가 등락률, 같은 일봉 1회 조회 파생) + 실집행 통합 라벨 `exec_leg_ret`/`exec_leg_venue`(NXT: 19:50→08:03, KRX: 15:20→09:03, 1분봉 첫 체결가)
  └► 선정/비선정을 가르는 요인 + rule 별 최적 청산창(시가/고저/종가·08:06 프리마켓·실집행 venue)을 사후 측정하기 위한 균일 결과 라벨(비선정 후보의 반사실 포함)
평일 09:40 rule_evaluator ─► 활성 가설(edge_rule)을 유니버스+market_snapshot 에 매일 적용 → `exit_label`(기본 `exec_leg_ret`)로 edge_rule_daily(페이퍼 성적) 누적 → 누적 stats·승격/강등 알림
  └► 학습 루프의 심장. candidate 로 등록→매일 자동 채점→표본·신뢰구간 충족 시 관리자 API 로만 live 승격(자동 승격 없음). 집행 연결은 Phase 4
  └► 초기 카탈로그는 sql/8. seed_edge_rules.sql 로 시드(control_legacy_top10=live 기준선 · F1~F4 candidate · veto_bad_news live · veto_overheat_gap candidate — 19:50 피처(nxt_gap_pct)라 선정 시점 실행 불가, edge_policy 게이트가 승격 차단). 인과 근거·registered_at(표본 시작일) 포함, INSERT IGNORE 라 재실행해도 등록일 보존
  └► 시간외·리스크 가설은 sql/14. seed_after_hours_rules.sql 로 시드(2026-07-09, id 27~31: f6_ah_react_up·veto_ah_react_down·veto_short_surge·veto_credit_high·f5_exec_str_strong — 전부 candidate, 17:50 수집 컬럼이라 선정 시점 실행 불가=페이퍼 전용, 임계값은 7/9 유니버스 p90 실측으로 사전 등록). family `f6_ah` 는 edge_policy FAMILIES 에 등록
  └► live 승격 규율(edge_policy 단일 소스): selector 는 n≥min_sample·CI하한>0·live 대조군 우위(부재 시 fail-closed)·선정 시점 실행 가능성 전부 충족 + 월 2개 상한 + 관리자 승인. veto 는 통계 면제(reduce-only)·실행 가능성만. benchmark(대조군·수급 밴드) 는 전 게이트 면제지만 실전 투입 알림/화면 대상에서 제외(기준선 교체는 API 로 수동). 19:50/익일 피처 rule 은 페이퍼 검증 전용 — 집행 설계(선정 시점 이동) 변경 후 재검토
주말 weight_tuner ─► 실현손익 + 지표(콘텐츠·뉴스 포함) 피드백 ─► 가중치 제안
  └► 0 근처 가중치는 절대스텝 부트스트랩 클램프로 성장 가능(±15% 곱셈식이 0을 0에 고정하는 문제 해소)
  └► backtest(core/backtest.py)로 판별력 검증 → IMPROVES=status 'pending'(승인 대상) /
     그 외(WORSENS·NEUTRAL·INSUFFICIENT)=status 'archived'(비적용 — 과적합이라 승인 대상은
     아니지만 '튜너 동작 여부' 확인용으로 대시보드에 표시)
  └► 매 실행 [건강지표] 로깅: 현재 가중치의 스프레드(승-패)·점수↔손익 상관(양수 전환 시 튜닝 재개 신호)
  └► 관리자 승인 시 승인 시점 backtest 재검증 — WORSENS 는 기본 차단(force=true 로만 강제) → 승인 시 strategy_config 반영
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
