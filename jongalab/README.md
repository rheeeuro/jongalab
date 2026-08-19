# jongalab — 메인 앱 (분석 · 스크리닝 · 매수신호 · 대시보드)

콘텐츠(유튜브/텔레그램/뉴스)를 LLM 으로 분석하고, 수급·기술적 지표로 종목을 점수화해
**일일 리포트**와 **종가베팅 매수 신호**를 만든다. FastAPI 백엔드(`:8000`) + Next.js 프론트(`:3000`) +
통합 스케줄러/PM2 cron 워커로 구성된다. 시세·수급은 직접 키움을 부르지 않고 `kiwoom/` 데이터
서버(`:8001`)를 HTTP 로 호출해 받는다.

**경계**: jongalab 은 **무엇을 살지** 결정해 `trade_signal` 에 적재만 한다.
**언제·얼마나·어떻게** 집행하는지는 `trading/` 도메인 책임이다.

> 이 README 는 **현재 구조와 상태**의 소스 오브 트루스다. `core/`·`routers/`·`workers/` 의 책임·흐름·
> 엔드포인트·안전장치를 바꾸면 이 파일도 함께 갱신한다.
> **판정 이력·백테스트 수치·기각 근거는 여기 쓰지 않는다** — [`docs/history/`](../docs/history/) 에 축별로 남긴다.
> 작업 규칙·가드레일·검증 절차는 루트 [`AGENTS.md`](../AGENTS.md) 를 따른다.

---

## 코드 구조

```
jongalab/
├── api.py            # FastAPI 진입점 — 라우터 등록(include_router)
├── core/             # 비즈니스 로직 + 데이터 접근(repository)
├── routers/          # HTTP 엔드포인트 핸들러
├── workers/          # 백그라운드 잡 (통합 스케줄러 + PM2 cron)
├── sql/              # jongalab DB 스키마 (1.create_database → 2.create_table → 마이그레이션)
└── frontend/         # Next.js 대시보드 (frontend/README.md 참고)
```

### `core/` — 비즈니스 로직

| 파일 | 책임 | 현재 상태·불변식 |
|---|---|---|
| `config.py` | `.env` 로딩, DB(jongalab/trading)·AI·키움/KIS 설정 | ⚠️ `.env` 를 바꾸면 **상시 프로세스를 재시작**해야 반영된다(스케줄러가 물고 있던 env 가 자식 잡에 상속됨). PM2 cron 잡은 매 spawn 시 `.env` 를 새로 읽어 재시작 불필요 |
| `db.py` | 컨텍스트 매니저 | `get_db`(jongalab) / `get_trading_db` |
| `ai_service.py` | **LLM 추상화(`analyze_content`)** — Ollama(콘텐츠 분석) / OpenAI(다이제스트·라벨) 분기 | 직접 SDK 호출 금지. LLM 은 구조화 JSON 만 내보내고 `build_analysis_markdown()` 이 마크다운을 재조립. 반환 규약: 일시적 실패=None(재시도 가치), 주식 무관 확정=`sentiment_score=-1`(호출부가 저장 없이 스킵). OpenAI 모델은 **`OPENAI_MODEL` 한 곳**이고 추론 모델이라 `temperature` 대신 `reasoning_effort`(`OPENAI_REASONING_EFFORT`, 기본 `none`)를 넘긴다 → **판정은 결정론이 아니다** |
| `ai_utils.py` | LLM 응답 파싱 | JSON 추출, 코드펜스/`<think>` 제거 |
| `trading_engine.py` | **종가베팅 분석 엔진** ⚠️민감/가드 | Phase 1 사전 스크리닝(양시장 통합 거래대금 순위·시총) → Phase 2 정밀(수급 그레이드·정배열/신고가·대장주·테마·콘텐츠·뉴스·등락률) → 종합점수·top-N. ⚠️ 운영 파라미터는 DB `strategy_config` 값이라 이 파일 기본값과 다르다 |
| `prompts.py` | 콘텐츠 분석 프롬프트 ⚠️민감/가드 | 구조화 출력(sentiment_score·tldr·tags·summary·stocks·strategy·related_companies) |
| `kiwoom_client.py` | 키움 데이터 서버(`:8001`) HTTP 클라이언트 | 기본/상세/수급/차트/주도주/분봉 |
| `kis_client.py` | 한국투자증권 Open API | 코스피200 선물 시세·WS 키. 원본은 `inquire_futures_daily_ohlc`(일봉)·`inquire_futures_minute_ohlc`(**당일** 1분봉, ~120봉/페이지라 되짚어 페이지네이션하고 당일 시초를 넘으면 멈춘다) |
| `market_data.py` | 통합 시세 조회 | 국내→키움, 선물→KIS, 지수/원자재/환율→yfinance. `fetch_index_ohlc()` 분봉 OHLCV(프리·애프터 포함, 전 심볼 KST 변환) · `/api/market-index-history/{symbol}?range=` 는 `1d`→(1d,1m)·`5d`→(5d,5m)·`1mo`→(1mo,30m). **코스피200 선물(K200NF·K200DF)은 yfinance 에 없어** `_kospi200_futures_candles()` 로 조립하고 두 카드가 **하나의 연속 시계열**을 공유한다(`1d`=야간세션 DB + 오늘 주간세션 KIS 분봉, 그 외=KIS 일봉). 30s TTL 캐시(빈 결과는 캐시 안 함). `fetch_edge_market_snapshot()` 시장 스냅샷 1행(지수·선물·프록시 + `_news_tone_today()` 로 당일 거시·섹터 뉴스 톤 — 19:50 호출이라 **매수 시점에 알 수 있었던 값**이고 사후 라벨로 덮지 않는다) · `fetch_us_extended()`(→`/api/us-extended`) US 프록시 정규장+프리/애프터(60s 캐시) |
| `sector_resolver.py` | 티커→섹터 해석 | ticker_dictionary 캐시, TTL 1년 |
| `ticker.py` | 콘텐츠 분석 기업명 → 종목코드 해석(`get_tickers`) | **`ticker_dictionary` ACTIVE 행만 근거**로 삼는 인메모리 인덱스(TTL 1시간). 매칭은 공백·기호·대소문자를 무시하는 정규화 비교까지만(`한미 반도체`→`한미반도체`) — 웹 검색·부분일치 추측 없음. 사전에 없는 이름(해외기업·비상장·제품명·업종어)은 **국장 코드가 없으므로 제외**하고 로그만 남긴다(그 이름뿐인 콘텐츠는 `should_save_content(allow_no_ticker=False)` 에서 스킵). 별칭(`LG엔솔`·`네이버`)은 관리자가 사전에서 **ACTIVE 로 승인**해야 잡힌다 — `PENDING` 은 해석에 쓰지 않는다. 반환 `name` 은 입력 이름 그대로(`save_content_analysis` 가 `stocks[].name` 에 티커를 붙이는 키) |
| `news_matcher.py` | 뉴스 헤드라인 → 종목 **사전매칭**(LLM 없음) | ticker_dictionary(ACTIVE) 인메모리 매처. 경계 룩어라운드 + `[]`·`【】`·`()` 제거로 오탐 억제. **적재는 텔레그램 경로 전용**(네이버는 종목코드 조회). `mentions_ticker(text, ticker)` 는 반대 방향 — 종목이 정해진 기사의 **제목 귀속 확인**용(재료 판정 코퍼스 선별) |
| `naver_news_client.py` | 네이버 증권 뉴스 클라이언트 | 경로 2개, **반환 계약 동일**(`[{headline, source_url, channel_name, published_at}]`) — ① `fetch_stock_news(code)` 종목별 JSON(관련기사 묶음 평탄화, `officeId/articleId` 안정 URL, `datetime` 분 단위, `titleFull`, `body` 발췌) ② `fetch_section_news(date, page)` 증권 섹션 **EUC-KR HTML** 목록(하루 56~75페이지 × 20건). HTML 파싱은 **제목 앵커 위치로 잘라** 조각 안에서 언론사·시각을 찾는다(문서 전체 findall+zip 은 하나만 빠져도 전건이 밀려 조용히 오염된다). 403/429 는 `NaverNewsBlocked` 로 올린다. ⚠️ HTML 이라 마크업 변경 시 예외 없이 빈 리스트 → 감지는 호출부의 '1페이지 0건=실패' 규칙 |
| `news_material_judge.py` | **뉴스 재료 지속성 벌크 판정**(OpenAI) | 판정 질문은 하나 — "오늘 이 재료를 본 사람이 **내일 아침에도** 이 종목을 살 만한가". 사실 축(`next_milestone`·`milestone_horizon`·`amount_locked`·`material_size_eok`→비율·`driver_scope`·`stage`)만 묻고 등급 `news_durability` 는 **코드가 결정론적으로 합성**(`derive_durability`). **합성 규칙 v2**(`news_durability_v`=2, 순서=우선순위): ① stage=마무리→소진 ② 다음 사건이 1개월 내→연속 ③ 다음 사건+산업사이클→연속 ④ 다음 사건만→중립 ⑤ 다음 사건 없음+stage 판정됨→소진 ⑥ 그 밖 None. `next_milestone` 결측이면 None(미판정). 코퍼스 = `NEWS_JUDGE_LOOKBACK_DAYS`(5일) 헤드라인 + 리드문, **날짜별 배분 후 리드문 있는 기사 우선**, 제목 귀속 확인·시세보도(`is_price_report`)·채널 복제 제외. 금액은 **억원 단위**로 묻고 비율만 저장. 판정 근거 `news_label_reason` 은 **사용자 화면에 노출되는 문장**이라 항목명·코드값 금지. ⚠️ 등급 정의나 **판정 모델이 바뀌면 rule `registered_at` 을 리셋**해 표본을 분리한다. 테스트 `tests/test_news_material_judge.py` |
| `sector_news.py` | 미매칭 뉴스 → 섹터·거시 라벨 | **관측 전용 — 점수·시드·veto 무영향.** 산업·정책·거시 어휘 **화이트리스트** 프리필터(한글 부분일치, ASCII 약어만 토큰 경계) 통과분만 LLM 이 섹터 확정·방향 판정. 섹터 어휘는 유니버스 어휘로 **고정**(조인 실패 방지), 방향은 척도 앵커(85/70/55/50/45/30/15)로 강제. 테스트 `tests/test_sector_news.py` |
| `dart_client.py` | DART 전자공시 OpenAPI | `list_filings(YYYYMMDD)`(유가 Y·코스닥 K, `_MAX_PAGES`=30, `stock_code` 없는 항목 제외) + `piicDecsn`(유상증자 **증자방식**) + `fricDecsn`(무상증자 **신주배정기준일**·배정비율·신주상장일 = 권리락일 파생의 유일한 정확한 근거). status `013`=빈 목록으로 정규화, 시장 하나가 실패해도 나머지는 반환 |
| `disclosure_events.py` | 공시 보고서명 → **사건 분류**(순수 함수, LLM 없음) | 정규식 테이블 `_RULES`(**첫 매칭 승 = 순서가 우선순위**) → `event_type`·`direction`(+1/0/-1)·`is_veto_type`·`is_subject`. **`direction`(악재 기록)과 `severe`(live veto)는 다른 축** — 악재는 전부 기록하고 실탄은 검증된 것만. 세 집합: `SEVERE_TYPES`(live) / `DILUTION_TYPES`(candidate) / 나머지 관측. ⚠️ **유상증자는 보고서명으로 판단 금지** — `유상증자미상`(veto 아님)으로 두고 `refine_capital_increase()` 가 `ic_mthn` 으로 확정(주주배정·일반공모→veto / 제3자배정→관측 / **조회 실패→미상 = veto 안 함**). 좁혀둔 4가지: `발행절차`·`시장조치`(실질 사유만 `상장위험`)·`풍문해명`·`is_subject`(종속·자회사 건은 direction·veto 0). `[기재정정]`은 `is_correction` 으로 `summarize()` 집계 제외. 테스트 `tests/test_disclosure_events.py` 가 실제 report_nm 표기로 계약 고정 |
| `news_veto_judge.py` | **보유 종목 밤사이 중대 악재 판정**(OpenAI) | 돈이 걸린 판정이라 로컬 Ollama 불사용. severe 발동은 `is_actionable`(confidence ≥ `NEWS_GUARD_MIN_CONFIDENCE`=85) 통과 시만, 형식 불량 응답은 None(무효) — 절대 발동으로 새지 않는다(`validate_verdict`). 테스트 `tests/test_news_veto_judge.py` |
| `filters.py` | 분석 결과 저장 여부 판단 | 점수 범위·티커 포함·환각 검증 |
| `backtest.py` | 가중치 제안 백테스트 | `score_candidate` 공식을 미러링(`recompute_score`)해 제안 가중치를 재적용. ⚠️ 엔진 공식 변경 시 미러도 갱신(테스트가 드리프트 감지) |
| `edge_predicate.py` | **predicate 평가기**(순수 함수, DB 무의존) | 조건 AND 결합(op 9종, `market.` 접두사로 market_snapshot 참조, **NULL=매칭실패**). `validate_predicate` 로 저장 전 검증. 테스트가 계약 고정 |
| `edge_selection.py` | **선정 레이어**(순수 함수) | `select_signals(mode, ...)` — `EDGE_SELECTION_MODE`(legacy/hybrid/rules)별 selected 판정 + veto(reduce-only, 전 모드) + `rule_names` 귀속. 점수·rank_no·저장은 불변. **hybrid 우선순위**: ① 표 수(매칭 live selector 수 + legacy 점수 top-N 1표) → ② 성적(지목한 rule 중 최고 `stats.mean_net`, legacy 표는 `legacy_mean_net`) → ③ 점수(rank_no). ⚠️ 같은 피처에 문턱만 다른 rule 을 등록하면 한 축이 2표를 만든다 |
| `edge_policy.py` | **Edge Ledger 정책 단일 소스**(순수 함수) | ① `rule_role`·`ROLES`·`FAMILIES`(도메인 8종) 레지스트리 ② **레이어별 실행 가능성** — `SELECTION_TIME_COLS`(선정 시점) → 'selection', +`EXECUTION_TIME_COLS`(19:50 NXT 스냅샷) → 'execution', 둘 다 아니면 None=페이퍼 전용. `market.` 축은 컬럼별로 `SELECTION_TIME_MARKET_COLS`(현재 `sox_ret`·`spx_ret`)만 허용한다 — **판정 기준은 접두사가 아니라 "14:30 수집값과 19:50 수집값이 같은가"**다. 채점은 19:50 저장값으로 하므로 시각에 따라 값이 달라지는 축(선물·VIX·환율·코스피/코스닥)을 열면 채점 표본과 집행 값이 어긋난다. 미국 정규장 지수는 한국시간 06:00 에 확정돼 그날 안에는 변하지 않는다. ⚠️ **화이트리스트에서 빠진 컬럼을 쓰는 rule 은 조용히 영구 승격 불가**가 된다 — 새 선정 시점 컬럼은 `_analysis_row`·`SELECTION_TIME_COLS`·(필요 시 `_PRESERVE_ON_NULL`) **세 곳을 함께** 고치고, 그 값이 실제로 선정 시점에 **행에 실려 있는지**(수집 시각·`closing_bet` 캐리포워드)도 함께 확인한다. 선정 가능한 rule 은 집행으로 내리지 않는다 ③ 승격 게이트 `check_promotion` — 정책 2종(`EDGE_PROMO_POLICY`, 함수 기본값은 fail-safe `strict`; 운영값 `experimental` 은 `t_days`·판정 일정만 면제). 자는 **절대 평균수익 계열**: selector = `mean_net`>0 + `n_days`≥`PROMO_MIN_DAYS`(10) + `ci_low`>0 + `t_days` ≥ `day_t_threshold(n_days)`(거래일 자유도 단측 95% t, None=fail-closed) + 실행 가능성. veto = `n_days`≥10 + 제외 종목 `mean_net`<0(일 클러스터 t 면제 — 가치가 평균이 아니라 꼬리 차단에 있다). benchmark 는 전 게이트 면제·알림 제외. 초과 계열은 계산하되 **화면·수동 검토 전용** ④ **판정 일정** `DISCOVERY_DAYS`=10·`CONFIRM_DAYS`=10 — 발견창 통과 시 확인창의 새 표본으로 `check_confirmation(stats, role)`(selector 양수 / veto 제외 종목 음수, 표본 부재는 fail-closed), **판정일에 1회만** 결론. `decision` 은 영구 기록이고 자동 전이 없음 ⑤ 강등 신호 `demotion_signal`/`check_demotion` — **자는 시장 회귀 잔차 `recent_alpha`**(승격의 절대 `mean_net` 과 다르다: 승격은 "돈을 버는가", 강등은 "시장 덕이 아니라 실력으로 벌던 게 끊겼는가"). `recent_n`≥`DEMOTE_MIN_N`(20)·`recent_n_days`≥5 + 역할별 부호(selector `alpha`<0 / veto 제외 종목 `alpha`>0). 표본 미달·`recent_alpha`=None(초과 기준선 부재)은 **fail-closed**이고 `demotion_signal` 이 그걸 `measurable=False` 로 구분해 낸다 — 전이는 양방향이라 "성적이 괜찮다"와 "판정할 표본이 없다"를 섞으면 무근거 복귀가 난다. 절대 수익은 시장과 동기화되고(하락 구간엔 전 룰이, 상승 구간엔 아무도 안 걸림) 초과수익은 `beta`=1 을 강제해 저beta 방어형 룰을 상승장에서 죽인다 — 둘 다 기각한 경위는 `docs/history/edge-ledger.md` ⑥ **운용 전이** `decide_transition` — `live ↔ paused` 를 평가기가 **자동으로** 굴린다(사람 승인 없음). 같은 방향 신호가 `TRANSITION_STREAK`(2) **표본일** 연속일 때 전이하고 반대 신호가 오면 카운트를 리셋한다. 단위가 달력 평일이 아닌 이유는 표본 없는 날엔 `alpha` 가 갱신되지 않아 같은 값이 두 번 세어지기 때문이다. `measurable=False` 면 상태·카운트를 모두 동결한다(fail-open: 갓 승격한 룰은 live 유지). 테스트 `tests/test_edge_policy.py` |
| `edge_features.py` | **선정 시점 피처 파생**(순수 함수, DB 무의존) | 결측=None(predicate NULL 규약과 맞물림). 수급 구조: `afternoon_ret`·`prog_buy_days`·`vol_ratio`. 종목 속성: `is_bio`(키움 업종명 '제약' + 사명 키워드 + 예외 코드 3단). 차트 레벨: `dist_prior_high_pct`(250일 전고점, **당일 봉 제외** — 포함하면 급등주가 자기 자신이 전고점이 된다)·`round_dist_pct`·`ma5_reclaim`. 외인 서지: `days_since_frgn_surge`(**당일 제외**)·`red_candle`·`red_candle_streak`. 매물대: `overhead_vol_ratio`·`poc_dist_pct`. 프로그램: `prog_cum_net`(tm 09:00~15:35 가드 — 키움 최근 거래일 폴백 오염 방지). 재무: `financials`(ka10001 응답 재사용, 추가 콜 0) + 파생 `op_earnings_yield`(영업이익÷시총). 호가: `order_book_features`(`ob_imbalance`·`ob_fpr_imbalance`·`ob_spread_pct`, 연속장 밖엔 None). 테스트 `tests/test_edge_features.py` |
| `daily_ohlc.py` | 수정주가 일봉·분봉 파싱 + **라벨 아티팩트 가드** 공유 모듈 | `SANE_RET_PCT`=±35%. **라벨 경로는 반드시 이 모듈만** 쓴다(기준이 어긋나면 청산창 비교가 오염된다). **권리락 가드 `is_price_scale_shifted`** — 수정 일봉은 권리락을 소급 조정하지만 분봉·NXT·`krx_close_price` 는 실거래가라, 미조정 가격 라벨만 배정비율이 손실로 찍힌다. 공시일로는 판정 불가라 **수정 일봉 종가 ↔ 실거래 종가 스케일 불일치**(허용 `PRICE_SCALE_TOL_PCT`=2%)로 감지 |
| `notifications.py` | 텔레그램 알림(재시도 포함) | `send_analysis_alert` 만 **parse_mode=HTML**(원문 인용 전달 형태: 헤더 → `<blockquote expandable>` 원문 → 🤖 tldr → 링크), `send_journal_post` 만 **평문**(게시글 초안이라 마크다운 기호를 살려 보내고, 4096자를 넘으면 줄 경계로 나눠 여러 통), 나머지는 Markdown. 길이 안전장치: 원문 2500자·코멘트 800자 절단 + 이스케이프 팽창까지 계산해 4096자 상한 안으로 재절단. 봇은 멤버가 아닌 채널 메시지를 전달할 수 없어 네이티브 전달은 불가 |
| `market_calendar.py` | KRX 개장일 판별 | exchange_calendars XKRX + **`EXTRA_HOLIDAYS` 수동 오버라이드**(신규 공휴일은 trading 쪽 복제본에도 함께 추가) + `holidays_in_month`(한글 이름) + `prev_trading_day`/`next_trading_day`(달력 조회 실패 시 무한 루프를 막는 14일 상한) |
| `logging_setup.py` | 로그 설정 | — |

#### `core/repository/` — DB 접근 계층 (raw SQL 은 반드시 여기서만)

`content` · `news` · `stock_event` · `source` · `ticker` · `stock_report` · `sector_report` ·
`market_snapshot` · `trade_signal` · `trade_result` · `strategy_config` · `weight_tuning` ·
`edge_rule` · `kis_token` · `kis_night_future` · `kis_night_future_bar` · `telegram_user` ·
`job_run` · `macro_event` · `news_veto` · `ex_rights` · `news_sector` · `sec_news` · `trading_position`

계층 규칙(어기면 게이트를 우회하는 두 번째 유입로가 생긴다):

| 대상 | 규칙 |
|---|---|
| `news` (`news_mention`) | 소스 2개가 한 테이블(텔레그램=사명 매칭 / 네이버=`source='naver'`, 매칭 없음). **모든 조회 함수는 `_source_filter(kind)` 를 통과한다** — `kind="count"`→`NEWS_COUNT_SOURCES`(기본 `telegram`, **동결**: 카운트 계열은 소스를 늘리면 계단식으로 튀고 그 표본을 live veto 가 쓴다) / `kind="text"`→`NEWS_TEXT_SOURCES`(기본 `telegram,naver`). 새 함수에 kind 를 빠뜨리면 TypeError(기본값 없음). "카운트를 세면 count, 텍스트를 읽으면 text" |
| `news_sector` | **관측 전용** — 조회 함수는 검정·감사용 집계 하나뿐, **live 경로에서 import 금지** |
| `sec_news` | **표시 전용** — 라벨·rule·veto·점수 경로에서 import 금지. news_mention 과 달리 **기사 1행**이라 화면 페이징이 SQL 한 번으로 정확 |
| `trading_position` | trading DB `position` **읽기 전용**(news_guard 의 보유 종목 조회 전용, 쓰기 금지) |
| `edge_rule` | `get_universe_label_totals(label)` 은 평균이 아니라 **(합계, 개수)** 를 돌려준다 — rule 마다 뺄 매칭 종목이 달라 여기서 평균을 내면 '자기제외'를 못 한다. label 은 `ALLOWED_EXIT_LABELS` 화이트리스트 검증(컬럼명이라 바인딩 불가) |
| `stock_event` | 종목×사건 1행 정규화, **영구 보존**. `(source, source_key=접수번호)` UNIQUE 로 멱등 |
| `ex_rights` | `(ticker, ex_rights_date)` PK 멱등. trading·gap_check 가 읽기 전용 조회 |
| `news_veto` | `news_veto_verdict` upsert 시 severe 는 GREATEST 로 **1→0 강등 금지** |

### `routers/` — 엔드포인트

`admin`(인증) · `contents` · `market` · `stock_report` · `news` · `source` · `strategy_config` ·
`weight_tuning` · `telegram_user` · `job_runs` · `ticker` · `edge_rule`.
새 라우터는 `routers/` 에 만들고 `api.py` 의 `include_router` 로 등록한다.

| 엔드포인트 | 계층 | 내용 |
|---|---|---|
| `/api/news/heat` | 집계(count) | 뉴스가 몰린 종목. 정렬은 건수가 아니라 **자기 기저 대비 배수**(`surprise` = 건수 ÷ 직전 7일 일평균, 분모 하한 1) — 건수 정렬은 시총 랭킹이 된다. `?date=` 면 그 날 하루, 없으면 최근 `?hours=` |
| `/api/news/materials?date=` | 집계 | 그 날 뉴스가 있던 유니버스 종목의 재료 라벨(비선정 포함 — 뉴스 화면의 축은 '그 날 뜬 재료') |
| `/api/news/stream?date=&limit=&offset=` | **표시(sec_news)** | 그 날 증권 섹션 기사 최신순 + `total`/`has_more`. 종목 칩은 사명 매칭 결과라 **없는 기사가 많다(실측 64% — 시황·환율·정책)** |
| `/api/news/{ticker}` | 표시(text) | 종목별 당일 헤드라인 |
| `/api/market-index-history/{symbol}?range=` | — | 지수/심볼 캔들 히스토리 |
| `/api/macro-events` | — | `?days=`(향후) / `?month=YYYY-MM`(그 달 전체·과거 포함) |
| `/api/market-holidays?month=` | — | 그 달 KRX 휴장 평일 + 한글 이름 |
| `/api/us-extended` | — | US 프록시 정규장+프리/애프터(trading 게이트가 소비) |
| `/api/stock-report/record-summary?days=` | 집계 | 최근 N 거래일 선정 종목 누적 성적(승률·평균 갭·평균 실체결·최고/최악일). 모집단은 `gap-stats` 와 같은 **selected=1 + 갭 체크 완료**(rank_no 로 자르지 않는다). ⚠️ `exec_leg_ret` 은 매매 경로 가동 이후 구간에만 있어 갭과 창이 다르므로 `exec_days`·`exec_from_date`·`exec_to_date` 를 함께 내려보낸다 |
| `/api/stock-report/{date}` | 표시 | 그 날 **선정 종목**(`selected=1`). 정렬은 **규칙 수 내림차순 → rank_no 오름차순**(`repository.stock_report.RULE_COUNT_SQL`) — 화면·텔레그램이 이 순서를 그대로 쓰고 다시 정렬하지 않는다. 유니버스 전체를 보는 경로(`include_unselected=True`, 엣지 연구용)는 `rule_names` 가 선정 종목에만 있어 **rank_no 순을 유지**한다 |
| `/api/stock-report/top-picks?dates=` | 표시 | 날짜별 **대표 추천 종목**(성적 달력용) = `selected=1` 중 위와 같은 정렬의 첫 종목. 예전엔 `rank_no=1`(selected 필터 없음)이라 추천에 없는 종목이 대표로 나왔다 |
| `/api/job-runs` | admin | 스케줄러 잡 실행 이력 |
| `/api/edge-rules` | GET 공개 / POST admin | 스코어보드. `/{id}/matched?days=`(≤90) 날짜별 매칭 종목 이력. 등록 시 `title`(한글 카드 제목)·`description`(초심자용 인과 근거) 필수, `family`·`role` 은 레지스트리 검증. 승격은 `edge_policy.check_promotion` 단일 소스 — 미충족 409+사유, **force 없음**. 라우터가 추가로 검사하는 건 **판정 일정 규율**(`decision.verdict=='confirmed'` 아니면 409) 하나이고, 이건 `EDGE_PROMO_POLICY=='experimental'` 에서 면제된다 — 그 정책에선 **발견 통과만으로 승격 가능**하다(평가기 알림도 같은 시점에 온다). 상태 전이는 **두 축**이다 — 원장(사람): `/{id}/promote`·`/{id}/retire`·`/{id}/unretire`(retired→candidate, `registered_at` 을 오늘로 밀어 **표본 리셋** — 같은 표본 재시험 금지), 운용(자동, 수동 개입용): `/{id}/pause`·`/{id}/resume`. paused 는 `list_rules(status='live')` 에 안 잡혀 선정·집행에서 자동으로 빠지고 채점은 계속된다 |

⚠️ 새 뉴스 엔드포인트를 붙일 땐 **집계(news_mention)냐 표시(sec_news)냐**를 먼저 정한다.
화면의 기사 수(1,000건대)와 재료 집계(배수)의 모집단이 다른 것은 **의도된 설계**다.

### `workers/` — 백그라운드 잡

실행 계층은 둘이다.

- **`scheduler`(통합 잡 스케줄러, PM2 상시 앱 `jongalab-scheduler`)** — 저위험 cron 잡 **13개**(아래 ⏰)를
  cron 시각마다 **서브프로세스**(`uv run workers/<잡>.py`)로 spawn 한다. 스케줄·타임아웃은
  `workers/scheduler.py` 의 `JOBS` 가 소스 오브 트루스. 매 실행을 `job_run` 에 기록하고 실패 시 관리자
  텔레그램 경보. misfire 유예를 넘긴 지각 실행은 스킵, `max_instances=1`, 타임아웃 kill 은
  **프로세스 그룹 단위**(`start_new_session`+`killpg`). 수동 1회 실행 `--once <잡>`.
  잡 코드 변경은 다음 실행에 자동 반영되지만 **`scheduler.py` 자체 변경은 재시작이 필요**하다(배포 훅이 수행).
  **중단 감시는 스케줄러 밖에서 2단계**: ① trading watchdog(평일 09:35)이 `job_run` 최신 기록 2시간 초과
  시 경보(지연 감지) ② `scheduler_watchdog`(PM2 cron, 5분)이 `pm2 jlist` 로 상태를 봐 자동 재기동(즉시 복구).
- **PM2 cron**(스케줄은 루트 `ecosystem.config.js`) — 상시(telegram)·창 민감/자금 인접 잡
  (gap_check·closing_bet·news_guard·night_futures·token-refresh)과 trading 도메인 전체.

| 워커 | 스케줄 | 역할·현재 상태 |
|---|---|---|
| ⏰ `youtube_collector` | 15분 | 채널 RSS → 자막 → Ollama 분석 → `content_analysis`. 저장 안 하기로 **확정된** 영상은 `content_skip` 에 기록(재분석 방지), 일시적 실패는 기록하지 않아 재시도. 타임아웃 방어 3중: `RUN_BUDGET_SEC`=300 소프트 데드라인 · `OLLAMA_TIMEOUT`=480s · 같은 영상 연속 `MAX_ANALYSIS_TIMEOUTS`=3회면 확정 스킵(**타임아웃만** 카운트 — 인프라 장애가 정상 영상을 영구 스킵시키지 않게) |
| `telegram_listener` | 상시 | Telethon 감시. **일반 채널**(platform=telegram)→LLM 분석→`content_analysis` / **뉴스 채널**(platform=news)→LLM 없이 사전매칭→`news_mention`. 세션 파일 공유 불가라 한 프로세스이고, **LLM 은 `asyncio.to_thread`+세마포어 1**(Ollama CPU 직렬, 처리량 ~24건/시간). 유입 조절 3단: ⓪ 감시 채널의 **전달(forward) 메시지**는 `content_skip('forwarded')` — 기준 집합은 기동 시 1회 해석하고 **경로별로 분리**(일반은 telegram 집합만, 뉴스는 news 집합만; 교차로 거르면 분석이나 언급이 사라진다) ① `DEDUP_TTL_SEC`=6h 동일 본문 dedup ② 대기 큐 `MAX_PENDING_ANALYSIS`=40 초과분 폐기(`backlog` 가 계속 잡히면 채널을 줄이거나 경량 경로로 옮기라는 신호). ⚠️ 감시 목록은 **기동 시 1회** 읽으므로 채널 추가·삭제 후 재시작 필요 |
| `news_guard` | 평일 07:00~09:25 (5분) | **뉴스 베토 감시** — 보유 종목 × 전거래일 15:00 이후 `news_mention` 을 OpenAI 판정 → `news_veto_verdict` upsert + severe 시 관리자 알림. trading monitor 가 severe=1 을 읽어 개장 즉시 전량 매도. 이미 확정·신규 없음은 스킵(호출 0~10회/아침), 보유 0 이면 자체 종료. 실패 시 기록 없이 재시도(판정 없음 = 미개입, 09:28 백스톱 유지) |
| ⏰ `disclosure_collector` | 평일 08:20~20:50 (:20/:50) | **DART 공시 수집** → 룰 분류 → 유상증자 건만 `piicDecsn` 추가 조회 → `stock_event` INSERT IGNORE. **권리락 캘린더 적재**: `무상증자`·`권리락` 공시를 트리거로 `fricDecsn` 신주배정기준일 → `권리락일 = 기준일 직전 영업일`. 트리거 2개인 이유는 결정 공시(2~3주 전)가 정상 경로이고 권리락 공시는 보완 경로다. 자율공시 건은 조회가 비어 `source='inferred'` 로 공시일 직후 2영업일을 **과잉 등록**한다. `first_seen_at` 은 수집기 최초 관측 시각(±30분, 백필은 **00:00 센티넬**). 키 미설정·API 오류는 **exit 0 로 조용히 종료**(수집 공백 = veto 미개입). 백필 `--date` |
| ⏰ `naver_news_collector` | **매일** 08:45~20:45 (:15/:45) | **네이버 종목별 뉴스** — 대상(오늘 ∪ 전거래일 유니버스 ∪ 보유) 별 1페이지 → **당일 기사만** → `news_mention` INSERT IGNORE(`(source_url, ticker)`). `created_at` 에 **기사 발행시각**을 넣는다(수집 시각이 아니다 — 오후 창·오버나잇 창 판정의 기준). `body_preview`(리드문) 함께 적재. 소비 범위: **텍스트 게이트 포함 / 카운트 게이트 제외**. **거래일 가드 없음** — 당일 기사만 적재하는 구조라 연휴 재료를 그날 담지 않으면 재개장일 선정 시점에 라벨이 빈다(휴장일엔 오늘 유니버스가 없어 대상은 전거래일 유니버스 ∪ 보유). 403/429 만 사이클 조기 종료(exit 1). `--date`·`--limit`·`--dry-run` |
| ⏰ `sec_news_collector` | **매일** 08:05~20:35 (:05/:35) | **증권 섹션 뉴스(표시용)** — 섹션 목록 1페이지부터 순회 → 종목 칩 매칭 → `sec_news` INSERT IGNORE. **신규 0건 페이지에서 중단**(상한 `SEC_NEWS_MAX_PAGES`=8), 과거 보정은 `--full` 로 조기 종료를 꺼야 한다. **'1페이지 0건'은 실패(exit 1)** — HTML 파서가 조용히 비는 것을 감지하는 유일한 장치. **거래일 가드 없음** — 휴장일에도 증권 섹션은 기사를 정상 제공하므로 이 실패 규칙이 매일 그대로 유효하다. 날짜 기준은 `published_at`. `SEC_NEWS_ENABLED=0` 이면 뉴스 탭 헤드라인만 빈다 |
| ⏰ `news_ticker_seed` | 일 07:30 | ka10099 → `ticker_dictionary` ACTIVE 업서트 |
| ⏰ `cleanup_content` | 매일 04:00 | `content_analysis`·`content_skip` 3개월 + `news_mention`·`sec_news` `NEWS_RETENTION_DAYS`(기본 30) 이전 삭제 |
| `closing_bet` | 평일 08:30~20시(30분) | Phase 1/2 스크리닝 → **ETF/ETN 코드 기반 제외**(ka10099, 이름 키워드는 백업) → `daily_stock_report`(**유니버스 전체** 저장) + `trade_signal`(selected 만 핸드오프, `rule_names` 태깅). 저장은 **분석 컬럼만 upsert**(탈락 종목만 삭제)라 다른 워커의 관측 컬럼을 지우지 않고, 컬럼 목록은 **`_analysis_row` 키에서 파생**된다(두 목록이 어긋날 수 없게). upsert 정책 집합(`_FIRST_WRITE_WINS`/`_PRESERVE_ON_NULL`)에 분석 컬럼에 없는 이름이 있으면 raise. 저장 실패는 관리자 텔레그램 경보. 등락률 **부호 조건 없음**. 저녁 회차(15:40+)엔 `{code}_NX` 로 **그 시점 야간 갭**을 계산해 룰 평가 dict 에 넣지만 ⚠️ **DB `nxt_gap_pct` 에는 쓰지 않는다**(소유자는 19:50 패스 — 덮어쓰면 채점 축이 어긋난다). 선정은 `edge_selection`(`EDGE_SELECTION_MODE` 코드 기본 `legacy`, **운영은 `hybrid`**)이 정하고 점수·rank_no·저장은 불변. `rule_names` 는 `trade_signal` 과 `daily_stock_report` 양쪽에 태깅(화면이 '룰 선정' 배지 + 실제 점수 순위를 보여준다). veto rule 은 전 모드에서 선정 직전 제외. 30분 재실행 구조 덕에 저녁 공시가 반영되면 잔여 pending 이 `expired` 로 정리돼 19:30 NXT 매수에서 자동 탈락한다 |
| `gap_check` (`--market-snap`/`--base-krx`/`--base-nxt`/`--check-nxt`/`--label-nxt`/`--check-krx`) | 평일 14:30 / 15:20 / 19:50 / 08:03 / 08:06 / 09:03 | 실매매 청산 창과 동일 기준의 갭 측정(종목별로 자기 venue 창 하나만 채점). **19:50** 은 확장 관측 — 유니버스 전체에 NXT 스냅샷(`krx_close_price`·`nxt_price_1950`·`nxt_gap_pct`·`nxt_after_value`·`nxt_listed`) + `market_snapshot` 1행. **08:06** 은 연구 라벨 — `nxt_open_price`·`nxt_open_ret`(앵커=KRX 확정 종가), 실매매 08:03 과 시각·부하 분리. **권리락 조정**: 갭 확정일이 권리락일이면 기준가를 `전일가/(1+배정비율)`로 되돌려 측정하고 `gap_ex_rights_ratio` 기록(`source='inferred'`=ratio NULL 행은 조정하지 않고 경고만). 텔레그램 알림은 09:03 확정 후 하루 1회. **14:30 `--market-snap`**(`market_snapshot_pre_buy`)은 같은 `market_snapshot` 1행을 매수 **전에** 한 번 굽는다 — 그 전엔 당일 행이 19:50 에나 생겨 `market.*` 축을 쓰는 rule 이 선정에서 늘 무음이었다. 저장은 전체 덮어쓰기라 **최종값(=채점이 보는 값)은 19:50 것**이고, 그래서 선정에 허용되는 축은 두 시각 값이 같은 것뿐이다(아래 `edge_policy`) |
| ⏰ `outcome_backfill` | 평일 09:30 | 유니버스 전체에 **일봉 라벨 4종**(`next_open_ret`·`next_high_ret`·`next_low_ret`·`next_close_ret`, 같은 일봉 1회 조회 파생) + **실집행 통합 라벨**(`exec_leg_ret`·`exec_leg_venue` — NXT 19:50→08:03 / KRX 15:20→09:03, 1분봉 첫 체결가) 백필. **권리락 가드**: 다음 거래일이 권리락일이면 `is_price_scale_shifted` 로 감지해 `exec_leg_ret` 를 비우고 같은 원인으로 오염된 `nxt_open_*` 도 되돌린다(정리는 이 워커 한 곳에서). 일봉 4종은 양 끝이 조정 스케일이라 손대지 않는다. 실집행 레그는 `exec_leg_ret` 활성 rule 의 가장 이른 `registered_at` 이후만(활성 rule 없으면 건너뜀 — 폭주 방지). **재료 지속성 가격 채점**: `mat_run_ret_3d`(익일 시가→D+3 종가)·`mat_up_days` — 앵커가 익일 시가인 이유는 그게 청산점이라 이후 상승만이 순수한 측정이기 때문. **연구 전용**(현행 전략은 익일 시가 전량청산). **후속 재료 채점** `news_followup_days` 는 **참고값**(라벨 채점 전용, 수익 채점과 섞지 말 것) |
| ⏰ `after_hours_labels` | 평일 **14:30**(`--risk-only`) + **17:50**(전체) | 유니버스 전체에 **시간외 반응 + 리스크 라벨** UPDATE(관측 컬럼, 점수 무영향). ① `ah_price`·`ah_flu_rt`·`ah_volume`(세션 16~18시 **중**에만 값이 살아 있어 스냅샷·과거 백필 불가) + 파생 `ah_react` ② 리스크(전부 **T-1 확정치** = 누수 없음): `credit_remn_rt`·`short_wght`/`_5d`·`lend_remn`/`lend_irds_5d` ③ `exec_str`/`_5d` ④ `market_snapshot.ah_up3_cnt`/`ah_dn3_cnt`. **14:30 회차(`after_hours_risk_pre_buy`)는 ②만** 수집한다 — 값이 T-1 확정치라 수집 코드가 `dt < 오늘` 행만 고르고, 따라서 **17:50 회차와 같은 값**이 나온다(채점 표본 = 집행 값). 이 회차 덕에 ② 계열이 선정 시점에 존재해 `SELECTION_TIME_COLS` 에 들어간다. ①③은 당일 세션 값이라 14:30 엔 없다(저장이 COALESCE 라 건너뛴 컬럼은 보존) |
| ⏰ `rule_evaluator` | 평일 09:40 | **Edge Ledger 일별 채점(2-pass)**. pass1: **retired 포함 전 rule** 을 유니버스+`market_snapshot` 에 적용 → `exit_label` 결과 → `mean_net = 평균 − EDGE_COST_PCT` → `edge_rule_daily` upsert(catch-up: 라벨 미도래는 재시도, 14일 초과 시 n=0 sentinel 종결) + `registered_at` 이후 표본만으로 stats 재계산(`n_days`·`mean_net_days`(일 등가중, 쏠림 진단)·`t_days`·초과 계열·**시장 회귀 계열**·화면용 `promo_eligible`/`promo_blockers`/`promo_policy`/`decision_stage`). 시장 회귀(`_market_fit`)는 (그날 룰 일수익, 그날 자기제외 유니버스 평균)을 회귀해 `beta`·`alpha`·`t_alpha`·`recent_alpha`·`down_day_mean` 을 낸다 — **`beta` 는 누적 표본, `alpha` 만 최근 창**(10거래일로 beta 까지 추정하면 se≈0.29 라 판정 불가). 최소 5거래일·시장 분산>0 미만이면 전부 None(fail-closed). `recent_alpha` 만 전이 판정이 쓰고 나머지는 화면·수동 검토용. **최근 창은 적응형**(`_recent_window`) — 표본일 10개가 기본이되 `DEMOTE_MIN_N` 을 못 채우면 뒤로 늘린다. 창을 표본일 개수로만 고정하면 `n = 표본일 × 폭(1일당 매칭 종목 수)` 이라 **폭이 얇은 룰은 문턱을 영원히 못 넘어** 자동 전이 대상에서 영구히 빠진다(두꺼운 룰은 10일에서 이미 문턱을 넘어 창이 늘지 않는다). 조건 판정은 **서버만** 하고 화면은 렌더링만 한다. pass2: stats 가 신선해진 뒤 **두 축을 따로** 처리 — 원장 축은 `check_promotion` → 텔레그램 알림(승격 후보·집행 설계 필요는 **판정일에만**, `strict` 는 확인창 판정일 / `experimental` 은 라우터가 판정 일정을 면제하므로 **발견 판정일**. 줄의 `[확인창 확증]`/`[발견 통과 · 실험 적용]` 표기가 근거를 구분한다), 운용 축은 `decide_transition` 으로 **`live ↔ paused` 를 직접 전이시키고**(승인 없음) 결과를 사후 보고한다. 연속 카운트는 `stats.flip_streak` 에 남고 **새 표본이 있는 실행에서만** 갱신된다. 전이 알림엔 판정값 `alpha`·`beta`·하락일 성적과 두 가중을 병기하고, 부호가 갈리면 ⚠️쏠림 표시. 승격·retire 는 관리자 API 수동 |
| ⏰ `weight_tuner` | 토 08:00 | 지난주 실현손익(`SCORE_LOGIC_MIN_DATE`=2026-07-07 이전 주는 스킵) → GPT 가중치 제안 → backtest 검증: IMPROVES=pending(승인 대상) / 그 외=archived(비적용·표시용) + [건강지표] 로깅(스프레드·점수↔손익 상관 — **양수 전환 시 튜닝 재개 신호**) |
| ⏰ `macro_event_check` | 월 08:20 | `macro_event` 캘린더 고갈 감시 — **severity≥3**(실제로 감액하는 계열) 마지막 이벤트가 3주 내면 exit 1 + 경보(시드를 잊으면 게이트가 '이벤트 없음'으로 조용히 무력화된다). sev2 는 감액에 안 쓰여 감시 대상이 아니다(전체를 보면 더 멀리 시드된 sev2 가 sev3 고갈을 가린다). 연말마다 다음 해 일정 수동 시드 |
| ⏰ `sector_news_labeler` | 매일 20:30(백로그) + 평일 14:30·19:00(`--newest-first`) | 미매칭 뉴스(`content_skip` no_match) → `news_sector_label`. **관측 전용.** 프리필터 → 통과분만 벌크 판정. **프리필터 탈락분도 `scope='무관'` 으로 적재**(안 남기면 같은 행이 계속 조회돼 백로그가 안 줄고 통과율도 못 잰다). LLM 실패 배치는 적재하지 않고 다음 실행 재시도. **실행 두 종류**: 20:30 은 **오래된 것부터**(백로그 소화 — 표본의 연속성이 목적, 매일인 이유는 코퍼스가 주말에도 쌓이기 때문) / 14:30·19:00 은 **최신부터**(`sector_news_labeler_pre_krx`·`_pre_nxt`, limit 300) — KRX 15:20·NXT 19:50 매수 판단 시점에 그날 거시·섹터 기사가 라벨을 갖고 있게 한다. 20:30 만 있으면 라벨이 언제나 매수 뒤에 생겨 뉴스 축을 검정조차 할 수 없다. `--limit`/`--batch-size`/`--dry-run`/`--newest-first` |
| ⏰ `journal` | 매일 20:50(일간) + 토 10:00(주간) | **변경사항 저널** — git 커밋을 GPT 로 사용자 관점 안내문으로 바꿔 `docs/journal/{daily/YYMMDD,weekly/YYMM-n}.md` 에 저장 + 관리자 텔레그램 전송(스레드·링크드인 게시글 초안). 집계 창은 **날짜로 고정**(일간 D = D-1 20:50~D 20:50, 주간 = 직전 토~금 일간 파일 7개 재요약)이라 지각 실행해도 내용이 같고 하루가 한 파일에만 들어간다. 커밋 없는 날은 파일을 만들지 않고 exit 0. 저널 프롬프트는 워커가 직접 갖는다(`core/prompts.py` 는 콘텐츠 분석 전용 가드 파일). 산출물은 git 미추적(`.gitignore`). `--backfill`(과거 일괄, 알림 없음)·`--date`·`--force`·`--no-notify` |
| `kis_night_futures_ws` | 평일 18:00~새벽 | KIS WS 야간선물 체결 → ① `kis_night_future` 단일행 현재가(2초, trading futures_gate 소비) ② `kis_night_future_bar` **1분봉 이력**(전 체결 집계 — 샘플링하면 고저가 깎인다). 체결 없는 분은 봉을 만들지 않는다. 세션 종료·끊김 시 진행 중 봉 flush, 분봉 저장 실패는 스트림을 죽이지 않는다 |
| (토큰) `kis_token_refresh` | 매일 07:00 | 키움+KIS 토큰 갱신 |

---

## 핵심 도메인 흐름

```
콘텐츠(youtube/telegram) ──► content_analysis (sentiment, tldr, tags, stock_calls)

뉴스 속보 채널 ──사전매칭(LLM X)──┐
네이버 종목별 뉴스(30분) ─────────┴──► news_mention (+ 리드문 body_preview)
                                    │   소비 게이트 2개: 텍스트=telegram+naver / 카운트=telegram 동결
                                    ├► 07:00~09:25 news_guard ─► 보유 종목 밤사이 악재 판정
                                    │    → news_veto_verdict(severe=1) ─► trading monitor 개장 즉시 전량매도
                                    └► 선정 시점 재료 판정(5일 헤드라인+리드문, 제목 귀속·시세보도 제외)
                                         → news_durability(연속/중립/소진, v2) + 사실 축  ※ 점수 무영향
                                         → outcome_backfill 이 mat_run_ret_3d 로 사후 채점

증권 섹션 목록(30분) ──► sec_news ──► 뉴스 탭 헤드라인  ※ 표시 전용, 집계 경로 격리

DART 공시(30분) ──룰 분류(LLM X)──► stock_event (영구 보존)
                                    ├► 선정 시점 집계 → disc_bad_type ─► veto_disclosure_severe(live) 제외
                                    └► 무상증자 → ex_rights_schedule ─► trading 매수 스킵 / gap_check 기준가 조정

closing_bet (평일 08:30~20시, 30분)
  Phase 1  양시장 통합 거래대금 순위(ka10032 mrkt_tp=000) + 관심섹터 보강 · ETF/ETN 제외 · 기본필터
           └ 거래대금 하한은 순위 응답만으로 판정 → 시총 조회 **전에** 컷. 실질 컷은 MIN_TRADING_VALUE
  Phase 2  유니버스 전체 정밀분석 → 수급 + 정배열 + 신고가 + 대장주 + 테마 + 콘텐츠 + 뉴스 + 등락률
           └ 선정 시점 피처·라벨 적재(아래 표) → edge_selection(hybrid) → selected · rule_names
  ├─► daily_stock_report  (유니버스 전체 = 연구 표본. 기본 조회는 selected=1, 연구는 include_unselected)
  └─► trade_signal (pending, selected 만) ─► trading 도메인이 집행

14:30 sector_news_labeler(최신) ─► KRX 매수 전 그날 거시·섹터 라벨 최신화(관측 전용)
14:30 after_hours_labels --risk-only ─► T-1 확정 리스크 라벨(공매도·신용·대차) 선반영
14:30 gap_check --market-snap  ─► market_snapshot 1행 조기 적재
                                 (위 둘이 선정 시점 rule 이 그 값을 볼 수 있게 하는 회차 —
                                  19:50 회차와 같은 값인 축만 edge_policy 가 선정에 허용)
15:20 gap_check --base-krx     ─► KRX 기준가(state)
17:50 after_hours_labels       ─► 시간외·리스크 라벨 + market_snapshot breadth
19:00 sector_news_labeler(최신) ─► NXT 매수 전 라벨 최신화
19:50 gap_check --base-nxt     ─► NXT 기준가 + 유니버스 NXT 스냅샷 + market_snapshot 1행
                                 (뉴스 톤 `news_macro_tone`/`news_sector_tone` 도 이때 = 매수 시점 값)
20:30 sector_news_labeler      ─► 미매칭 뉴스 섹터·거시 라벨 백로그 소화(관측 전용)
익일 08:03/09:03 --check-*     ─► gap_* 확정 (NXT: 19:50→08:03 / KRX: 15:20→09:03)
익일 08:06 --label-nxt         ─► nxt_open_price·nxt_open_ret (연구 라벨, 실매매 경로와 분리)
익일 09:30 outcome_backfill    ─► 일봉 라벨 4종 + exec_leg_ret/venue + 재료 가격 채점
익일 09:40 rule_evaluator      ─► 전 rule 채점 → edge_rule_daily → stats → 승격 알림 / live↔paused 자동 전이
주말 weight_tuner              ─► 가중치 제안(backtest 게이팅) → 관리자 승인 시 strategy_config 반영
```

### 선정 시점 관측 컬럼 (전부 점수 무영향 — 연구·rule 입력용)

| 축 | 컬럼 | 소유 |
|---|---|---|
| 뉴스 집계 | `news_unique_count`·`news_pm_count`·`news_first_today`(창은 `_FIRST_TODAY_LOOKBACK_DAYS` 로 명시)·`news_prior_avg` | closing_bet |
| 뉴스 LLM | `news_sentiment`·`news_catalyst` + 지속성 사실 축 6종 → `news_durability`·`news_durability_v`·`news_label_reason` | closing_bet |
| 뉴스 파생 | `news_material_age_h`(당일 최신 재료 기사가 선정 시점 대비 몇 시간 전인가 — 결정론) | closing_bet |
| 공시 | `disc_count`·`disc_bad_type`·`disc_good_type` | closing_bet |
| 섹터 | `sector_rel_ret`·`sector_leader_chg` | closing_bet(저장 시점 파생) |
| 수급 구조 | `foreign_brokers_buying`·`prog_buy_days`·`afternoon_ret`·`theme_strength`·`frgn_exhaust_rate`·`frgn_exhaust_chg`·`vol_ratio`·`first_seen` | closing_bet |
| 차트 레벨 | `dist_prior_high_pct`·`round_dist_pct`·`ma5_reclaim` | closing_bet |
| 외인 서지 | `days_since_frgn_surge`·`red_candle`·`red_candle_streak` | closing_bet |
| 매물대 | `overhead_vol_ratio`·`poc_dist_pct` | closing_bet |
| 프로그램 | `prog_am_net`(정오 창, first-write-wins)·`prog_pm_net`(오후 창 차분) | closing_bet |
| 재무 | `fin_per`·`fin_pbr`·`fin_ev`·`fin_roe`·`fin_eps`·`fin_bps`·`fin_sales`·`fin_op_profit`·`fin_net_income` + 파생 `op_earnings_yield` | closing_bet |
| 호가 | `ob_imbalance`·`ob_fpr_imbalance`·`ob_spread_pct`(연속장 밖 None → PRESERVE_ON_NULL 로 마지막 세션값 보존) | closing_bet |
| NXT 스냅샷 | `krx_close_price`·`nxt_price_1950`·`nxt_gap_pct`·`nxt_after_value`·`nxt_listed` | gap_check 19:50 |
| 시간외·리스크 | `ah_*`·`credit_remn_rt`·`short_wght`/`_5d`·`lend_remn`/`lend_irds_5d`·`exec_str`/`_5d` | after_hours_labels |
| 결과 라벨 | `next_open_ret`·`next_high_ret`·`next_low_ret`·`next_close_ret`·`exec_leg_ret`/`_venue`·`nxt_open_ret`·`mat_run_ret_3d`·`mat_up_days`·`news_followup_days` | outcome_backfill / gap_check 08:06 |

---

## 유지보수 (주요 로직 변경 시)
1. 다음 5가지를 먼저 검토: ① 이 기능이 꼭 필요한가 ② 관련 기존 코드가 있는가 ③ 가장 단순한 구조는
   ④ 사용자가 가장 덜 헷갈리는 흐름은 ⑤ 어느 쪽이 더 유지보수하기 쉬운가.
2. 구현 전 이 README 의 해당 섹션 + [`docs/history/`](../docs/history/) 의 그 축 파일을 읽는다
   (이미 기각된 방향을 다시 제안하지 않기 위해).
3. 구현 후 바뀐 **책임·흐름·파라미터**를 이 README 에 반영하고, **판정 근거·수치는 `docs/history/`** 에 남긴다.
4. DB 접근은 `core/repository/*`, LLM 은 `core/ai_service.analyze_content` 만 사용한다.
5. 검증: Python 변경마다 `uv run --directory jongalab python -m py_compile <file>`,
   라우터/응답 변경 시 API 기동 후 `curl` 로 status·shape 확인.
6. 순수 로직 단위 테스트: `uv run --directory jongalab --group dev pytest`(DB/네트워크 없이).
   `recompute_score` 는 실제 `score_candidate` 와 교차검증되므로 엔진 공식 변경 시 함께 갱신.
