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
├── workers/          # 백그라운드 잡 (통합 스케줄러 + PM2 cron — 아래 workers 절 참고)
├── sql/              # jongalab DB 스키마 (1.create_database → 2.create_table)
└── frontend/         # Next.js 대시보드 (frontend/README.md 참고)
```

### `core/` — 비즈니스 로직
| 파일 | 책임 |
|---|---|
| `config.py` | `.env` 로딩, DB(jongalab/trading)·AI(Ollama/OpenAI)·키움/KIS 설정 |
| `db.py` | 컨텍스트 매니저(`get_db`, `get_trading_db`) — 안전한 연결 관리 |
| `ai_service.py` | **LLM 추상화(`analyze_content`)** — Ollama(콘텐츠 분석)/OpenAI(다이제스트) 분기. 직접 SDK 호출 금지, 항상 여기로. LLM 은 구조화 JSON(tldr/tags/summary/stocks/strategy)만 내보내고 `build_analysis_markdown()` 이 `analysis_content`(마크다운)를 재조립. 반환 규약: 일시적 실패(파싱/LLM 오류)=None(재시도 가치 있음), 주식 무관 확정 판정=`sentiment_score=-1` 인 결과 — 호출부는 -1 이면 저장 없이 스킵 |
| `ai_utils.py` | LLM 응답 파싱(JSON 추출, 코드펜스/`<think>` 제거) |
| `trading_engine.py` | **종가베팅 분석 엔진** ⚠️민감/가드. Phase 1 사전 스크리닝(거래대금 통합 순위·시총) → Phase 2 정밀(수급 그레이드·정배열/신고가·대장주·테마·콘텐츠·등락률) → 종합점수·top-N. 2026-07-03 실증 반영: 등락률 항(2~12% 가점/15%+ 감점) 신설, 대장주 10→3·프로그램 10→0 축소, ka10131 연속수급 버그(_AL 접미사·코스피만·abs) 수정. 2026-07-07: 거래대금 후보 풀 30→50 확대, 테마 보너스는 거래대금 상위권 교집합에만 부여. 2026-07-28: 후보 조회를 양시장 통합 순위로 전환하고 `PREFERRED_TRADING_VALUE` 2000억→4000억(선정 547건/70거래일 일클러스터 t=+2.60), `TOP_N_BY_VALUE` 50→100(통합 순위 1페이지 = 행 윈도우 상한 — 실질 컷은 `MIN_TRADING_VALUE`) — 둘 다 DB `strategy_config` 값이라 이 파일 기본값과 다르다. 2026-07-06: 5일 수급점수에서 기관/외인 순매수 0(ka10059 잠정치 미반영 가능성)을 중립 처리 — 가점 없이 스트릭 유지, 순매도(<0)만 스트릭 리셋(당일 집계 지연이 연속매수 보너스를 무너뜨리던 문제 수정) |
| `prompts.py` | 콘텐츠 분석 프롬프트 ⚠️민감/가드. 구조화 출력(sentiment_score·tldr·tags·summary·stocks[방향/확신/시간축]·strategy·related_companies) |
| `kiwoom_client.py` | 키움 데이터 서버(`:8001`) HTTP 클라이언트 — 기본/상세/수급/차트/주도주 |
| `kis_client.py` | 한국투자증권(KIS) Open API — 코스피200 야간선물 시세, WebSocket 키 |
| `market_data.py` | 통합 시세 조회(국내→키움, 선물→KIS, 지수/원자재/환율→yfinance). `fetch_index_ohlc(symbol, period, interval, prepost)` 은 지수/심볼의 **분봉 OHLCV 시계열**(yfinance, 시장 카드 클릭→상세 차트용, `prepost=True`로 프리·애프터마켓 봉을 합치고 정규장 밖 봉은 `extended=True` 플래그, 시각은 전 심볼 KST 변환(정규장 밖 판정은 거래소 로컬 기준), 커스텀 K200 선물은 빈 배열)을 반환. `GET /api/market-index-history/{symbol}?range=` 는 `1d`→(1d,1m)·`5d`→(5d,5m)·`1mo`→(1mo,30m) 매핑(프론트 범위 토글). `fetch_edge_market_snapshot()` 은 표시용 경로를 재사용해 시장 스냅샷 1행(코스피/코스닥·NQ·SPX·SOX·VIX·환율·WTI·EWY·KORU·SKHY(하이닉스ADR)·K200 주야간선물)을 조립. `fetch_us_extended()`(→ `GET /api/us-extended`)는 US 프록시(SOXX·SKHY·EWY·KORU)의 정규장(`regular_ret`)+장 마감 후 프리/애프터(`extended_ret`)+`market_state`를 반환(60s 캐시) — trading 종가베팅 NXT 매수 게이트(프리마켓 최근등락)·아침 하드손절 강화(오버나잇 정규장 결과)가 소비 |
| `sector_resolver.py` | 티커→섹터 해석(ticker_dictionary 캐시, TTL 1년) |
| `ticker.py` | 기업명↔티커 변환, 신규 티커 등록, 콘텐츠 본문 기업명 추출 |
| `news_matcher.py` | 뉴스 헤드라인 → 종목 사전매칭(LLM 없음). ticker_dictionary(ACTIVE) 인메모리 매처, 경계 룩어라운드 + 발행처 대괄호([]·【】) 제거로 오탐 억제 |
| `news_material_judge.py` | **뉴스 재료 지속성 벌크 판정**(OpenAI `complete_json`, temperature=0). 뉴스가 있는 유니버스 **전건**(≈16종목/일)에 요약·방향(`news_sentiment`)·유형(`news_catalyst`) + **지속성 4축**을 붙인다. 2026-07-29 에 `news_summary.py`(Ollama 단건 요약, 하루 최대 5행)를 **대체**했다 — 같은 컬럼을 채우는 경로가 둘이면 어느 쪽이 만든 라벨인지 알 수 없다. **왜 지속성인가**: 종가베팅은 익일 개장 청산이라 다음 날 아침 살 사람이 필요하고, 가설은 "수치가 이미 확정된 단발 이벤트는 종가에 소진되고 다음 마일스톤이 남은 연속 재료는 이어진다"다. 실측 단서(7/01~27, n 작아 근거 아님): 정책테마 익일 시가 +3.68%·장중 **+0.15%p** / 임상승인 +2.47%·**+3.12%p** vs 실적 −2.03%·−2.16%p / 수주계약 −1.77%·−3.31%p (유니버스 −0.08%·−1.66%p) — 연속 재료만 장중에 죽지 않았다. **왜 LLM 이어야 하나**: '언급의 지속'은 `news_mention` 카운트로 공짜지만 재보니 시총 프록시였다(대형주는 매일 아침 기사가 난다). 재료 자체의 지속성은 DB 에 프록시가 없어 텍스트를 읽어야 나온다. **'지속성 점수' 하나를 묻지 않는다** — 감(感)이면 오탐 육안 감사가 불가능하다. 관측 가능한 **사실 4축**(`news_next_milestone` 남은 다음 예정 사건 · `news_amount_locked` 수치 확정·소진 여부 · `news_driver_scope` 종목단독/산업사이클 · `news_stage` 첫발표/진행/마무리)을 묻고 등급 `news_durability`(연속/중립/소진)는 **코드가 결정론적으로 합성**한다(`derive_durability`, 순서=우선순위). 필수 3축 중 하나라도 결측이면 **None**(미판정) — '중립'으로 눕히면 결측이 표본을 오염시킨다. 판정 근거 한 문장은 `news_label_reason` 에 남겨 감사한다 — 이 문장은 **리포트 상세에 그대로 노출되는 사용자 문장**이므로 프롬프트가 판정 항목명·코드값(`next_milestone=0` 등)을 문장에 쓰지 말라고 못박는다(2026-07-29 — 초기 프롬프트가 '육안 감사용'으로만 규정해 LLM 이 필드명을 그대로 썼고, 그게 사이트에 노출됐다. 이미 저장된 행은 소급 불가라 프론트 `lib/news.humanizeMaterialReason` 가 화면에서 치환한다). **판정 근거는 5일치 헤드라인**(`NEWS_JUDGE_LOOKBACK_DAYS`) — 당일만으로는 `stage`(첫 발표인지 세 번째 후속인지)를 알 수 없다. 뉴스가 몰린 종목은 최신 N건이 전부 당일 기사가 되므로 `select_headlines` 가 **날짜별로 먼저 배분**하고 남은 예산을 최신에서 채운다(SK하이닉스 실측 당일 64건 — 분산 없이는 룩백이 무의미) + 동일 본문(공백 정규화) 채널 복제 제거. 한계: 저장된 건 헤드라인 500자 + 링크 프리뷰뿐이고 **본문이 없어** 마일스톤 '날짜'는 판정 불가(존재 여부만 묻는다). 프롬프트는 가드 파일과 분리. 단위 테스트 `tests/test_news_material_judge.py` |
| `dart_client.py` | **DART 전자공시 OpenAPI 클라이언트** — 공시검색(`list.json`) + 유상증자 상세(`piicDecsn.json` → `capital_increase_methods`, 접수번호별 **증자방식**)를 감싼 최소 래퍼(토큰 발급 없음, `DART_API_KEY` 쿼리 인증). `list_filings(YYYYMMDD)` 가 유가(Y)·코스닥(K) 하루치를 페이지 끝까지(`_MAX_PAGES`=30) 수집하고 `stock_code` 없는 항목(비상장 계열사)은 제외. status `013`(데이터 없음)은 빈 목록으로 정규화하고 그 외 오류만 `DartError`. 시장 하나가 실패해도 나머지는 반환(부분 수집 허용) |
| `disclosure_events.py` | **공시 보고서명 → 사건 분류**(순수 함수, LLM 없음). DART `report_nm` 은 표준화돼 있어 정규식 테이블(`_RULES`, **첫 매칭 승 — 순서가 곧 우선순위**)만으로 `event_type`·`direction`(+1/0/-1)·`is_veto_type`·`is_subject` 를 낸다. **`direction`(악재 기록)과 `severe`(live veto)는 다른 축이다** — 둘을 묶으면 `veto_bad_news` 처럼 "veto 안 하는 타입은 라벨조차 안 남아 영영 측정 불가"에 빠진다. 악재는 전부 `direction=-1` 로 기록하고(→ `disc_bad_type` 후보), 실탄(live veto)은 검증된 것만 태운다. 세 집합: `SEVERE_TYPES`(live, 존속위험·불성실공시·횡령배임·계약해지 — 통설이 아니라 사실) / `DILUTION_TYPES`(candidate, 희석 계열 — 측정 중) / 나머지 악재(소송·자사주처분, 관측 전용). **⚠️ 유상증자는 보고서명으로 판단 금지**: 제목이 거의 항상 '주요사항보고서(유상증자결정)'이라 배정방식이 안 드러나는데 방식에 따라 방향이 정반대다(주주배정·일반공모=희석 악재 / 제3자배정=전략적 투자 유치로 호재 가능). 2026-07-27 NAVER 의 NVIDIA 대상 제3자배정(1.48조, 희석 4.6%)이 상승했는데 제목 기반 분류는 이를 악재로 보고 **그날 1순위 종목을 제외할 뻔했다**. → `유상증자미상`(veto 아님)으로 두고 수집기가 `piicDecsn` 로 `ic_mthn` 을 조회해 `refine_capital_increase()` 로 확정한다(주주배정·일반공모→`유상증자` veto / 제3자배정→`유상증자제3자` 관측 / **조회 실패→미상 그대로 = veto 안 함**). 실측(6거래일): 비정정·당사자 유상증자 8건이 **전부 제3자배정** — 제목 기반이었다면 8건 전부 오탐이었다. 이 반증 때문에 희석 계열 전체(CB·BW·EB·감자 포함)를 live 에서 내려 candidate 로 측정한다(sql/38). `NEGATIVE_TYPES` 는 `_RULES` 파생이 아니라 명시 목록이다(`유상증자`는 정규식으로 도달 불가). **2026-07-28 첫 실수집 오탐 감사로 좁힌 4가지**(각각 회귀 테스트 고정): ① `발행절차`(발행결과·효력발생·발행가액확정·감자완료 — 결정은 며칠 전에 났으니 새 정보 아님) ② `시장조치`(거래정지·해제·관리종목우려 — 대다수가 액면병합·주식분할·무상증자·SPAC합병 같은 **기술적** 정지이고 해제는 정상화 신호. 실질 위험 사유(`상장폐지`·`상장적격성`·`실질심사`)만 `상장위험` veto) ③ `풍문해명`(풍문·조회공시 — '풍문또는보도에대한해명'은 삼성전자·SK하이닉스급에도 흔한 부인 공시라 방향 미정) ④ **`is_subject`**(종속회사·자회사·출자법인 건은 접수 종목의 사건이 아니다 — 초기 가정 "공시는 stock_code 로 당사자 확정"이 틀렸다. `event_type` 은 남기고 `direction`·`veto` 만 0 으로 눕혀 관측). 소송·자사주처분·유상증자제3자(방향 갈림)도 관측만 — 과잉 veto 는 기회비용. `[기재정정]`·`[첨부정정]` 은 `is_correction` 으로 분리해 `summarize()` 집계에서 제외(원 공시는 접수일에 이미 처리 — 정정을 세면 엉뚱한 날 같은 종목이 또 제외된다. 실측상 유상증자 41건 중 33건이 정정이라 이 필터가 없으면 오탐이 4배). `summarize(events)` → `disc_count`/`disc_bad_type`/`disc_good_type`. 단위 테스트 `tests/test_disclosure_events.py` 가 실제 report_nm 표기로 계약 고정 |
| `news_veto_judge.py` | **보유 종목 밤사이 중대 악재 판정**(OpenAI `complete_json`, temperature=0 — 돈이 걸린 판정이라 로컬 Ollama 불사용). news_mention 헤드라인만 근거로 '시초가 갭하락이 거의 확실한 중대 악재'(FDA 불승인·계약 파기·횡령·거래정지류) 여부를 JSON 판정. severe 발동은 `is_actionable`(confidence ≥ `NEWS_GUARD_MIN_CONFIDENCE`=85) 게이트 통과 시만 — 형식 불량 응답은 None(무효, 재시도)으로 절대 발동으로 새지 않는다(`validate_verdict`). 프롬프트는 가드 파일과 분리. 단위 테스트 `tests/test_news_veto_judge.py` |
| `filters.py` | 분석 결과 저장 여부 판단(점수 범위·티커 포함·환각 검증) |
| `backtest.py` | 가중치 제안 백테스트 — `score_candidate` 공식을 미러링(`recompute_score`)해 저장된 표본에 제안 가중치를 재적용, 승자/패자 판별력 비교. ⚠️엔진 공식 변경 시 미러도 갱신(테스트가 드리프트 감지) |
| `edge_predicate.py` | **Edge Ledger predicate 평가기**(순수 함수, DB 무의존). `evaluate(predicate, row, market)` — 조건 목록 AND 결합(op 9종: == != > >= < <= between in not_null, `market.` 접두사로 market_snapshot 참조, NULL=매칭실패). `validate_predicate` 로 저장 전 검증. 단위 테스트 `tests/test_edge_predicate.py` 가 계약 고정 |
| `edge_selection.py` | **선정 레이어**(순수 함수). `select_signals(mode, candidates, live_rules, veto_rules, top_n, market)` — `EDGE_SELECTION_MODE`(legacy/hybrid/rules)별 selected 판정 + veto(reduce-only, 전 모드) + rule_names 귀속. 점수·rank_no·저장은 불변. 단위 테스트 `tests/test_edge_selection.py` |
| `edge_policy.py` | **Edge Ledger 정책 단일 소스**(순수 함수). ① rule 역할 판정(`rule_role`: 명시 `role` 컬럼(selector/veto/benchmark) 우선, 구 스키마는 family 겸용 매핑 폴백 — closing_bet 선정·라우터 검증이 공유. `ROLES`/`FAMILIES`(도메인 8종 — 2026-07-10 `f7_risk` 종목 리스크 속성 추가) 레지스트리. 2026-07-09 sql/15 로 role·family 분리: 수급 밴드 4종은 role=benchmark(측정 도구가 실탄 승격되는 경로 차단), veto 는 도메인 family+role=veto. 2026-07-29 sql/42 로 **음의 가설 2종**(`f5_retail_solo_pump`·`f3_nxt_gap_thin`)을 selector→**veto** 재분류: 음의 가설을 매수 축에 두면 게이트 부호가 반대로 붙어 **가설대로 손실이면 침묵**(veto 전환 근거가 쌓여도 알림 없음)·**가설과 반대로 이익이면 🟢승격 후보**(착시 검증용 rule 이 실탄 매수 후보)가 된다 — f5_retail_solo_pump 가 7/29 실제로 그 상태였다(mean_net +1.90%, 일 t=1.18, 평균의 전부가 이틀에서 나옴). role·family 는 분류 메타데이터라 채점 이력(predicate·registered_at·edge_rule_daily)과 무관하지만, **selector 기준으로 찍힌 `decision` 은 무효라 NULL 로 되돌려 재판정**한다) ② 선정 시점 실행 가능성(`selection_executable` — 19:50/익일 수집 피처를 쓰는 rule 은 선정 때 NULL→무음 no-op 라 live 부적격) ③ 승격 게이트(`check_promotion(rule, controls, policy)` — **정책 2종**(`config.EDGE_PROMO_POLICY`, 함수 기본값은 fail-safe 로 `strict`): `strict` 는 통계 유의성(`ci_low_exc`>0 + `t_days_exc`≥t분포임계값) + 판정 일정 강제, `experimental`(2026-07-28 현재 운영값)은 **그 둘만 면제**하고 거래일≥10·**절대 순수익>0**·**초과수익>0**·대조군 우위·실행 가능성은 유지. experimental 근거: 현행 legacy 선정이 무엣지가 아니라 **실제로 마이너스**(실측 14거래일 — 무작위 10종목이 legacy 를 82.8% 이김, 유니버스 평균 +0.071% vs legacy -0.150%, 점수 최하위 10종이 legacy 보다 +0.556%p) → 챔피언이 마이너스면 도전자 오탐의 기대 비용이 낮으므로 올려보고 강등하는 편이 낫다. 안전망은 절대/초과 하한 + 강등 감지(최소 5거래일). 롤백은 값을 `strict` 로. **질문이 둘이라 자도 둘**: "돈을 버는가"는 **절대**(mean_net>0), "우연이 아닌가"는 **초과**(ci_low_exc·t_days_exc). 절대만 보면 그 기간 장이 오른 몫을 실력으로 착각하고(유니버스 기간 평균 +0.320%·양수일 7/14, 잡음도 2배라 유의성 미달), 초과만 보면 돈 잃는 rule 이 통과한다. 상세: selector 는 **절대 수익성**(원시 `mean_net`>0 — 2026-07-28 추가. 초과 계열만 보면 '유니버스보다 낫지만 돈은 잃는' rule 이 통과하고(실측 f5_late_day_strength 절대 -0.39%/초과 +0.20%, f8_op_earnings_yield -0.76%/+0.15%) 대조군 우위로도 막히지 않는다 — 대조군 자체가 -0.227% 라 문턱이 음수. 손실 최소화가 1순위이므로 '덜 잃는 쪽'이 아니라 '버는 것만' 올린다. **가중은 종목-일(`mean_net`) — 시드 배분을 반영하지 않는다**: rule 채점이 유니버스 전체 대상이라 매칭 종목-일 대부분은 사지도 않은 종목이고('그날 계좌 수익률' 개념이 성립 안 함), 시드 배분은 바뀌므로(SEED_MAX_NAME_PCT 50%→25% 이력) 측정이 배분에 의존하면 배분 변경 시 과거 점수가 무효가 된다 — 가설 검증은 집행 방식과 분리한다. `mean_net_days`(일 등가중)는 **진단값**으로 함께 저장: 둘의 격차가 크면 수익이 매칭 많은 날에 쏠렸다는 신호(실측 f5_frgn_surge_pullback1 종목-일 +0.950% vs 일 등가중 -0.745%)이고, 그 쏠림은 유의성 쪽에서 `t_days_exc`(일 등가중)가 잡는다. 대조군 우위·강등도 **같은 자(mean_net)** 를 쓴다 — 한쪽만 바꾸면 가중이 다른 값을 견주게 된다)·거래일 수(`n_days`≥`PROMO_MIN_DAYS`=10, 종목-일 클러스터링 과신 방지 — **`min_sample`(종목-일)은 2026-07-28 게이트에서 제외**: 단위가 거래일 규율과 어긋나 통계적으로 가장 강한 좁은 룰을 막았다(f5_breakout_structure t=2.08·n=4, f4_theme_follower t=2.76·n=6). 컬럼은 참고값으로 유지)·`ci_low_exc`·**일 클러스터 t**(`t_days_exc` ≥ `day_t_threshold(n_days)` = **거래일 자유도의 단측 95% t 임계값** — 고정 1.65 는 소표본에서 너무 관대해서(거래일 10일이면 1.833, 5일이면 2.132) t 분포로 교체했다. None 은 fail-closed) — **둘 다 유니버스 자기제외 초과 계열**로 잰다(2026-07-28). 원시 ci_low 는 종목-일 iid 가정이라 같은 날 시장 무브 상관만큼 과신하고, PROMO_MIN_DAYS 는 문턱만 세울 뿐 CI 는 그대로였다(이 게이트 없이 후보로 올라와 수동 재계산에서 뒤집힌 사례 2건: f5_prog_persistent 7/27 iid t=1.82→일 t=0.47, f4_sector_follower 7/28 1.99→0.37). **veto 는 일 클러스터 t 면제** — reduce-only 라 최악이 기회비용이고 가치가 평균이 아니라 꼬리 차단에 있다(veto_bio_kosdaq 은 대체효과 t=0.95 로 평균 유의성이 없는데도 HLB 하한가 꼬리 때문에 유지가 맞았다 — 평균 t 를 요구하면 정작 필요한 보호 veto 가 후보로도 못 올라온다))·**live 대조군 우위**(`mean_net` **원시** 기준 — 통계 유의성은 초과로 보되 '현행 선정보다 나은가'는 절대 순수익으로 물어야 결정에 쓰인다. 부재 시 fail-closed), veto 는 **최소 실익 게이트**(n_days≥10 + 제외 종목 mean_net<0 — 2026-07-13 veto_bio 가 등록 당일 n=3 으로 매일 '승격 후보' 알림되던 구멍 봉합), 공통으로 실행 가능성 — 라우터 409 사유·평가기 알림·`stats.promo_eligible` 이 전부 이 함수에서 파생) ④ **판정 일정**(`DISCOVERY_DAYS`=10·`CONFIRM_DAYS`=10·`decision_stage`/`decision_due`/`check_confirmation`, sql/39, 2026-07-28): 게이트를 매 평일 재검사하면 룰 하나가 무기한 재시험을 쳐 오탐이 명목 5%→**22%**가 된다(모의: candidate 24종이 전부 무엣지여도 60거래일 내 최소 1건 발생 확률 99.8%·기대 5.2건 — 7/28 알림 4건 중 3건이 재계산에서 뒤집힌 원인). **롤링 창은 해법이 아니라 악화**(창 크기 고정이라 W거래일마다 새 시험 → 가짜 룰 200개 모의에서 롤링20은 90%가 후보로 뜸 vs 누적 32%). → 발견(누적 거래일 1~10) 통계 게이트 통과 시 확인창(11~20)의 **발견에 쓰지 않은 새 표본**으로 재확인하고 **판정일에 1회만** 결론. 오탐 2.4%. **확인창도 role 별로 자·부호가 다르다**(`check_confirmation(stats, role)`, 2026-07-29 수정 — 발견 게이트와 같은 자): selector 는 초과수익 `mean_exc`>0, **veto 는 제외 종목 원시 `mean_net`<0**. 이 구분이 없어 role 을 안 보고 `mean_exc`>0 만 요구하던 동안 veto 는 "제외할 종목이 시장을 이겨야 확증"이 되어 **잘 작동하는 veto 가 그 이유로 종결**될 상태였다(veto_short_surge: 확인창 표본 mean_exc -0.98%·제외 종목 mean_net -0.38% = veto 로선 정상 방향인데 confirm_failed 예정이었다). 표본 부재는 양쪽 모두 fail-closed. 발견 판정은 **통계만** 본다(선정 시점 실행 불가는 집행 설계 문제라 종결 사유가 아님 — `exec_blocked` 로 따로 기록). 판정 결과는 `edge_rule.decision`(영구 기록, stats 와 달리 재계산 대상 아님)에 남고 **자동 전이는 없다**(탈락 rule 의 retire 도 관리자 판단). ⑤ 강등 게이트(`check_demotion`: 최근 창 `recent_n`≥20·`recent_n_days`≥5 + **역할별 부호** — selector 는 매수 종목 `recent_mean_net`<0, veto 는 **제외 종목** `recent_mean_net`>0(이기는 종목을 버리는 중)일 때 후보. benchmark 면제. 2026-07-28 rule_evaluator 에서 이관: 부호를 selector 와 공유해 정상 작동하는 veto_bio_kosdaq(제외 종목 평균 -0.158% = 손실을 제대로 걸러낸 상태)을 매일 강등 후보로 올리던 오탐 수정). 단위 테스트 `tests/test_edge_policy.py` |
| `edge_features.py` | **F5 수급 구조 피처 파생**(순수 함수, DB 무의존). `afternoon_ret`(당일 13시 시간봉 시가→현재가 %)·`prog_buy_days`(최근 5일 중 프로그램 순매수일)·`vol_ratio`(당일 거래량÷20일 평균) — closing_bet 이 이미 수집한 응답에서 스칼라를 굽는다. 결측=None(predicate 의 NULL=매칭실패 계약과 맞물림). `is_bio`(2026-07-10, F7): 바이오/제약 분류 — 키움 업종명 '제약' + 사명 키워드 + 알려진 예외 코드 3단 판별(키움 upName 이 코스닥 바이오벤처를 '일반서비스'로 뭉뚱그리는 구멍 보완), `veto_bio` 계열 rule 이 참조. 차트 구조(2026-07-19): `dist_prior_high_pct`(250일 전고점(고가) 대비 거리 % — **당일 봉 제외**, 포함하면 급등주는 자기 자신이 전고점이 되어 매물벽 정보 소실; 직전 이력 20일 미만 None)·`round_dist_pct`(최근접 라운드피겨 1·2·5×10^k원 대비 부호 있는 거리 %)·`ma5_reclaim`(5일선 재탈환: 전일 종가 5일선 아래 → 당일 5일선 위 양봉) — 매물벽 음의 가설 `veto_prior_high_wall`·`veto_round_figure_cap` 과 돌파 대칭 쌍 `f5_prior_high_break`·`f5_round_figure_break`, 눌림목 반등 `f5_ma5_reclaim` 이 참조. 외인 서지 축(2026-07-19, sql/23·24 — 종가베팅 팁 PDF 통설 검증): `days_since_frgn_surge`(직전 거래일 중 외인 순매수≥100억 서지의 경과 거래일, 1=어제·최대 4, **당일 서지는 제외** — 당일 유입은 frgn_net_buy 가 이미 봄)·`red_candle`(당일 음봉=현재가<당일 시가 — 음전과 다른 정보, 갭업 후 밀림 포착)·`red_candle_streak`(당일 포함 연속 음봉 수, 당일 양봉=0 — "2음봉"을 전일 봉색까지 보고 판정) — 눌림 `f5_frgn_surge_pullback1`(수급 1음봉)·`f5_frgn_surge_pullback2`(수급 2음봉, 연속 음봉만 — 전일 양봉 후 반락은 인샘플 −1.16%라 제외)과 지속 `f5_frgn_surge_carry`(전부 selector candidate)가 참조. 매물대 프로파일(2026-07-19, sql/25 — 컬럼만, rule 은 레벨 축 판정 후): `overhead_vol_ratio`(250일 거래량 중 현재가 위 비중 0~1 — 일봉 고저 균등 배분 근사, 매물대 두터움)·`poc_dist_pct`(최대 거래 집중 가격대 POC 대비 거리 %). 프로그램 스냅샷(2026-07-19, sql/26): `prog_cum_net`(ka90008 최신 행 당일 누적, tm 09:00~15:35 가드 — 키움의 최근 거래일 폴백 오염 방지) — `f5_prog_pm_reversal` 이 참조. 재무 스냅샷(2026-07-22, sql/32): `financials`(ka10001 같은 응답 재사용, 추가 콜 0) — `fin_per`·`fin_pbr`·`fin_ev`(밸류에이션 배)·`fin_roe`(%)·`fin_eps`·`fin_bps`(원)·`fin_sales`·`fin_op_profit`·`fin_net_income`(억원). 분기 저속 데이터·점수 무영향, 부채비율은 ka10001 미제공. 파생 `op_earnings_yield`(2026-07-22, sql/34 — 영업이익(억원)×1e8÷시총(원), 결측/시총≤0=None): "영업이익이 시총 1/10은 돼야"(≥0.1) 통설의 predicate 화 — DSL 이 컬럼-상수만 되어 비율을 선정 시점에 미리 굽는다. `f8_op_earnings_yield`(f8_value/selector candidate, sql/35)가 참조. 호가 미시구조 스냅샷(2026-07-22, sql/33): `order_book_features`(ka10004 신규 엔드포인트, 선정 시점 후보당 1콜) — `ob_imbalance`(총매수÷총매도잔량)·`ob_fpr_imbalance`(최우선 잔량비)·`ob_spread_pct`(스프레드/현재가 %). 연속장 밖엔 잔량 0→None(repository PRESERVE_ON_NULL 로 종가 직전 마지막 세션값 보존). 두 축 모두 rule 은 데이터 축적 후 등록(현재 컬럼만). 단위 테스트 `tests/test_edge_features.py` |
| `daily_ohlc.py` | 수정주가 일봉(ka10081)·분봉(ka10080) 파싱 + 결과 라벨 아티팩트 가드(`SANE_RET_PCT`=±35%) **공유 모듈** — outcome_backfill(일봉·실집행 레그)·gap_check --label-nxt 가 함께 사용(라벨 간 유효성 기준이 어긋나면 청산창 비교가 오염되므로 라벨 경로는 반드시 이 모듈만) |
| `notifications.py` | 텔레그램 알림(재시도 포함). `send_analysis_alert` 만 **parse_mode=HTML** 이고 나머지 알림은 Markdown — 2026-07-29 콘텐츠 알림을 **원문 인용 전달 형태**로 바꾸면서(헤더 → `<blockquote expandable>` 원문 그대로 → 🤖 tldr 한 줄 → 대시보드/원문 링크) 원문의 임의 문자(`*`·`_`·`[`)가 Markdown 파싱을 깨 알림이 조용히 누락되던 문제도 함께 막았다(예외를 삼키고 로그만 남기는 구조라 눈에 띄지 않던 실패). 봇 계정으로는 네이티브 '전달'(forwardMessage)이 불가능하다 — 원문 수집은 Telethon **사용자 세션**, 발송은 **봇**이고 봇은 멤버가 아닌 채널의 메시지를 전달할 수 없다. 길이 안전장치: 원문 2500자·코멘트 800자 절단 + 이스케이프(`&`→`&amp;`) 팽창까지 계산해 4096자 상한 안으로 인용분을 재절단(엔티티 중간 절단 방지). 원문이 없는 경로(YouTube)는 기존 형태(제목 + 분석 본문) 유지 |
| `market_calendar.py` | KRX 개장일 판별(exchange_calendars XKRX + `EXTRA_HOLIDAYS` 수동 오버라이드 — 달력 데이터에 없는 신규 공휴일은 여기와 trading 쪽 복제본에 함께 추가) + 월별 휴장 평일·한글 이름(`holidays_in_month` — 리포트 캘린더 휴일 라벨용, XKRX 영문명→한글 매핑 + `EXTRA_HOLIDAY_NAMES`) |
| `logging_setup.py` | 로그 설정 |

#### `core/repository/` — DB 접근 계층 (raw SQL 은 반드시 여기서만)
`content`(콘텐츠 분석) · `news`(뉴스 속보 언급 `news_mention`) · `stock_event`(**사건 계층** — 종목×사건 1행 정규화, **영구 보존**. DART 공시 멱등 적재(`save_events`, `(source, source_key=접수번호)` UNIQUE)·일자별 벌크 조회(`get_events_by_date`)) · `source`(채널) · `ticker`(기업명↔티커, 상장종목 벌크 시딩) · `stock_report`(종목일간리포트 — 리포트 저장·갭 체크·NXT 스냅샷·결과 백필) ·
`sector_report`(주도 섹터) · `market_snapshot`(일 단위 시장 피처 — 지수·선물·VIX·환율·WTI·한국 프록시 EWY/KORU/SKHY, F2·레짐/지정학 프록시 연구용) · `trade_signal`(→ trading DB 매수신호 핸드오프, 멱등 upsert) ·
`trade_result`(trading.audit_log 실현손익 읽기) · `strategy_config`(점수 가중치·임계값) ·
`weight_tuning`(주간 GPT 제안) · `edge_rule`(가설 원장 CRUD·stats·일별 채점 edge_rule_daily. `get_universe_label_totals(label)`=날짜별 유니버스 (라벨 합계, 종목 수) — 평균이 아니라 합계·개수로 돌려주는 이유는 rule 마다 빼야 할 매칭 종목이 달라 여기서 평균을 내면 '자기제외'를 못 하기 때문. label 은 `ALLOWED_EXIT_LABELS` 화이트리스트 검증(컬럼명이라 바인딩 불가)) · `kis_token` · `kis_night_future` · `telegram_user` ·
`job_run`(스케줄러 잡 실행 이력 — start/finish 기록, 잡별 최신/최근 조회, 재시작 sweep·60일 정리) ·
`macro_event`(거시 이벤트 캘린더 조회 — 고갈 감시용 `last_event_time`, trading macro_gate 는 직접 읽기 전용 조회) ·
`news_veto`(뉴스 베토 판정 `news_veto_verdict` — news_guard 가 upsert(severe 는 GREATEST 로 1→0 강등 금지), trading monitor 는 직접 읽기 전용 조회) ·
`trading_position`(trading DB `position` 읽기 전용 — news_guard 의 보유 종목 집합 조회 전용, 쓰기 금지).

### `routers/` — 엔드포인트
`admin`(인증) · `contents`(콘텐츠) · `news`(뉴스 재료 — ① `/api/news/heat`: 최근 N시간 뉴스가 몰린 종목. **정렬은 건수가 아니라 자기 기저 대비 배수**(`surprise` = 건수 ÷ 직전 7일 일평균, 분모 하한 1) — 건수 정렬은 시총 랭킹이 되어 대형주가 상단에 고정됐다(2026-07-29 실측 하이닉스 95·현대차 57·삼성전자 43건). 오늘 유니버스 종목이면 재료 라벨(`durability`/`catalyst`/`summary`)도 함께 실어 카드가 '무슨 재료인지'까지 보여준다. ② `/api/news/materials?date=`: 그 날 뉴스가 있던 유니버스 종목의 재료 라벨 슬림 목록(비선정 포함 — 뉴스 화면의 축은 '오늘 뜬 재료'이고 매매 선정과 다르다), `/news` 탭용. ③ `/api/news/{ticker}`: 종목별 당일 헤드라인 + `is_price_report`(시세보도 여부 — 화면이 재료 기사를 먼저 보여주고 시세 기사를 접는다. 판별은 후속 재료 채점과 **같은 함수** `news_material_judge.is_price_report` 를 써서 화면과 채점 기준이 갈리지 않게 한다)) · `market`(주가/지수 + 지수 캔들 히스토리 `/api/market-index-history/{symbol}?range=1m|3m|6m|1y` — 시장 카드 클릭 시 `/market/{symbol}` 상세 차트용 + 거시 이벤트 `/api/macro-events` — macro_event 캘린더: 기본 `?days=`(향후, 마켓 카드·메인 '오늘 밤' 배너) / `?month=YYYY-MM`(그 달 전체·과거 포함, 리포트 캘린더 셀 마커·범례), 실패 시 빈 목록 + 휴장 평일 `/api/market-holidays?month=YYYY-MM` — 그 달 KRX 휴장 평일을 한글 이름과 함께, 리포트 캘린더 휴일 라벨용) · `stock_report`(리포트·갭) ·
`source`·`strategy_config`·`weight_tuning`·`telegram_user`·`job_runs`(스케줄러 잡 실행 이력 `/api/job-runs` — admin '워커 현황' 페이지용)(admin 전용) · `ticker`(조회 공개/수정 admin) ·
`edge_rule`(가설 원장 — GET 스코어보드 공개(daily 는 matched 제외 스칼라만+최신 매칭 1일치 별도, `/{id}/matched?days=`(≤90)로 날짜별 매칭 종목 이력을 별도 제공 — 종목별 change_pct·selected 를 리포트에서 조인해 복기 맥락 포함), POST 등록/승격/강등만 admin. 등록 시 `title`(한글 카드 제목)·`description`(인과 근거) 필수, `family`(도메인)·`role`(selector/veto/benchmark, 기본 selector)은 edge_policy 레지스트리로 검증 — 같은 family 가설이 늘며 카드 구분이 안 되던 문제로 2026-07-06 title 컬럼 추가(NULL 이면 프론트가 name 슬러그 폴백). 승격 게이트는 `core/edge_policy.check_promotion` 단일 소스 — 미충족 시 409+사유, force 없음, 대조군 부재 시 fail-closed. 라우터는 월 승격 상한(**3개** — 2026-07-28 experimental 정책 도입 시 2→3, live selector 1종으론 hybrid 가 legacy 와 거의 같은 종목을 사서 실험이 성립하지 않음) + **판정 일정 규율**(`decision.verdict=='confirmed'` 아니면 409 — stats 는 매일 재계산되므로 이걸 안 막으면 탈락 rule 이 우연히 게이트를 통과하는 날 승격돼 '시험 1회' 규율이 무의미해진다)을 추가 검사).
새 라우터는 `routers/` 에 만들고 `api.py` 의 `include_router` 로 등록한다.

### `workers/` — 백그라운드 잡
실행 계층은 둘이다 (2026-07-13 1단계 이관):
- **`scheduler`(통합 잡 스케줄러, PM2 상시 앱 `jongalab-scheduler`)** — 저위험 cron 잡 8개
  (아래 표에서 ⏰ 표시: collector·cleanup·seed·outcome_backfill·after_hours_labels·rule_evaluator·weight_tuner·macro_event_check)를
  cron 시각마다 **서브프로세스**(`uv run workers/<잡>.py`)로 spawn. 스케줄·타임아웃은
  `workers/scheduler.py` 의 `JOBS` 가 소스 오브 트루스. 매 실행을 `job_run` 테이블에 기록하고
  실패(exit≠0/타임아웃) 시 관리자 텔레그램 경보. misfire 유예를 넘긴 지각 실행은 스킵(창 민감 잡 보호),
  `max_instances=1` 로 중복 실행 방지. 타임아웃 kill 은 **프로세스 그룹 단위**(`start_new_session`+`killpg`)
  — `uv` 부모만 죽이면 python 자식이 고아로 남아 중복 실행·DB 중복키 충돌을 일으킨다(2026-07-15 사건).
  수동 1회 실행: `uv run workers/scheduler.py --once <잡>`.
  잡 코드 변경은 다음 실행에 자동 반영(매 실행 새 프로세스), **`scheduler.py` 자체 변경은 재시작 필요**(배포 훅이 수행).
  **중단 감시**(2단계, 스케줄러 자신은 죽으면 알리지 못하므로 모두 스케줄러 밖에서 돈다):
  ① trading watchdog(평일 09:35)이 `job_run` 최신 기록이 2시간 이상 오래되면 경보(2026-07-15 배포 훅
  재시작 끊김 → 이틀 무감지 중단 사고 재발 방지. 배포 훅도 재시작 후 online 검증·재시도를 하도록 보강).
  ② `scheduler_watchdog`(PM2 cron `jongalab-scheduler-watchdog`, 5분마다)이 `pm2 jlist` 로 프로세스
  상태를 확인해 online/launching 이 아니면 **자동 재기동 + 관리자 경보**(2026-07-21 PM2 데몬 전체 재시작 후
  scheduler 만 resurrect 실패로 3시간여 방치된 사고 대응). ①은 지연 감지(잡 이력 기반), ②는 즉시 자동복구(프로세스 기반).
- **PM2 cron**(스케줄은 루트 `ecosystem.config.js`) — 나머지: 상시(telegram)·창 민감/자금 인접
  잡(gap_check·closing_bet·night_futures·token-refresh)과 trading 도메인 전체. 스케줄러 검증 후 단계 이관 예정.

| 워커 | 스케줄 | 역할 |
|---|---|---|
| ⏰ `youtube_collector` | 15분 | 채널 RSS → 자막 → Ollama 분석 → `content_analysis`. 분석까지 갔지만 저장 안 하기로 **확정된** 영상(무관/기업없음/환각/티커없음)은 `content_skip` 에 기록해 재분석 방지(2026-07-15 — 미기록 시 15분마다 같은 영상을 Ollama 재분석해 잡 타임아웃). 일시적 실패(자막 미생성·LLM 오류)는 기록하지 않아 다음 주기 재시도. **잡 타임아웃 방어 3중(2026-07-21)**: ① 소프트 데드라인 `RUN_BUDGET_SEC=300` — 경과 300s 초과 시 새 채널 처리를 멈추고 clean 종료(남은 영상은 다음 주기가 이어받음, 유실 없음). ② LLM 호출 상한 `OLLAMA_TIMEOUT=480s`(core/config) — 분석 1건이 무한정 늘어져 잡 전체를 죽이는 것을 차단(300+480<840 이라 SIGKILL 원천 불가). ③ 같은 영상이 연속 `MAX_ANALYSIS_TIMEOUTS=3`회 LLM 타임아웃나면 `content_skip(reason='analysis_timeout')` 확정 스킵해 재분석 루프를 끊음. 타임아웃(`AnalysisTimeout`)만 카운트(`content_analysis_fail`, sql/31) — 연결 실패(Ollama 다운)·파싱 실패는 세지 않아 인프라 장애가 정상 영상을 영구 스킵시키지 않음 |
| `telegram_listener` | 상시 | Telethon 감시. **일반 채널**(platform=telegram)→ LLM 분석 → `content_analysis`. **뉴스 채널**(platform=news, 고빈도)→ LLM 없이 사전매칭 → `news_mention`. 감시 목록은 **기동 시 1회** `sources` 에서 읽으므로 채널 추가·삭제 후엔 `pm2 restart jongalab-telegram` 이 필요하다(2026-07-29 신규 16채널이 재시작 전까지 수집 0이었다). 두 경로가 한 프로세스인 이유는 Telethon 세션 파일을 두 프로세스가 공유할 수 없기 때문 — 그래서 **LLM 호출은 `asyncio.to_thread` 로 스레드에 내보내 이벤트 루프를 막지 않는다**(2026-07-29 채널 15→28 확장 대응. 이전 동기 호출은 분석(건당 평균 152초, CPU 추론) 동안 루프를 세워 뉴스 적재가 07~09시대 평균 145초·최대 22분 밀렸고, `news_guard` 의 개장 전 악재 판정이 09:28 청산 이후로 밀릴 수 있었다). 분석은 세마포어로 **동시 1건**(Ollama CPU 직렬 — 동시 실행은 서로 느려질 뿐) → 처리량 상한은 **시간당 ~24건**. 느린 원인은 **출력 토큰**이다(2026-07-29 실측, `ai_service._log_llm_cost` 가 호출마다 로깅): 입력 prefill 은 1,650~1,700토큰 = **5초**(지시문 3,352자 = 1,622토큰 + 원문)인데 출력 decode 가 **5.7 tok/s** 라 건당 평균 152초의 95%가 출력이다 → `num_ctx` 축소나 원문 길이 절단으로는 거의 못 줄이고(prefill 은 실제 토큰 수에 비례, num_ctx 는 KV 할당량일 뿐), **프롬프트가 요구하는 출력 필드 축소 또는 더 작은 모델**만 유효하다. 반대로 num_ctx(기본 4096)를 줄이면 프롬프트가 한도를 넘을 때 **앞쪽 지시문부터 잘려** JSON 형식 지시가 사라지고 파싱 실패가 된다(현재 여유 ~2,400토큰 ≈ 원문 5,000자까지 안전). 상한을 넘는 유입은 두 장치로 흘린다: ① `DEDUP_TTL_SEC=6h` 내 **동일 본문**(공백 정규화 SHA1)은 재분석 없이 `content_skip(reason='duplicate')` — 여러 채널이 같은 리서치/속보를 전달하므로 정보 손실 없는 절감 ② 대기 큐가 `MAX_PENDING_ANALYSIS=40` 을 넘으면 `content_skip(reason='backlog')` 로 폐기 + 경고 로그(쌓아두면 결과가 수 시간 뒤에 나와 재료 가치가 없다). `backlog` 건수가 계속 잡히면 LLM 경로 채널을 줄이거나 `platform='news'`(경량 경로)로 옮겨야 한다는 신호. 알림(점수 30~80 구간 제외)은 2026-07-29 부터 **원문 그대로 + tldr 덧붙임** 형태로 나간다(`notifications.send_analysis_alert` 에 `original_text`·`tldr`·`source_url` 전달) |
| `news_guard` | 평일 07:00~09:25 (5분 폴링, PM2 — 자금 인접이라 스케줄러 비이관) | **뉴스 베토 감시** — 보유 종목(trading.position 읽기 전용) × 전거래일 15:00 이후 `news_mention` 을 OpenAI(`news_veto_judge`)로 판정해 `news_veto_verdict` upsert + severe 확정 시 관리자 텔레그램. trading monitor 가 severe=1 을 읽어 개장 즉시(NXT 08시대/KRX 09:00) **전량 매도**. 이미 severe 확정·신규 헤드라인 없음은 스킵(LLM 호출 아침당 0~10회), 보유 0 이면 자체 종료. LLM/DB 실패 시 기록 없이 다음 폴링 재시도(판정 없음 = trading 미개입, settle 09:28 백스톱 유지). 수동 검증 `--once` |
| ⏰ `disclosure_collector` | 평일 08:20~20:50 (30분, :20/:50) | **DART 공시 수집** — `list_filings` 로 당일 유가·코스닥 공시 전체 → `disclosure_events.classify`(룰, LLM 없음) → 유상증자 건만 `piicDecsn` 로 증자방식 추가 조회(`_resolve_ic_methods`, 해당 회사만 부르므로 하루 10콜 안쪽) → `refine_capital_increase` → `stock_event` 에 `INSERT IGNORE`(접수번호 UNIQUE → 재실행 멱등). `first_seen_at` 은 **수집기 최초 관측 시각**(DART `list.json` 이 접수 '시각'을 안 줘서 접수시각 근사, ±30분) — "선정 시점에 이 공시가 이미 있었는가" 판정용. 과거 백필(`--date`)은 관측 시각을 알 수 없어 **그날 00:00 센티넬**을 쓴다(수집기는 08:20~20:50 에만 도니 00:00 은 실관측일 수 없다 → 백필분 식별 가능). closing_bet(:00/:30) 직전에 갱신되도록 스케줄을 어긋나게 뒀다. **키 미설정·API 오류는 exit 0 로 조용히 종료**(수집 공백 = `disc_*` NULL = veto 미개입 → 선정은 정상 동작). 과거 백필 `--date YYYYMMDD`(거래일 가드 우회) |
| ⏰ `news_ticker_seed` | 일 07:30 (등록 시 1회) | 키움 ka10099(코스피/코스닥) → `ticker_dictionary` ACTIVE 업서트. 뉴스 사전매칭 커버리지용 |
| ⏰ `cleanup_content` | 매일 04:00 | `content_analysis`·`content_skip` 3개월 + `news_mention` 14일 이전 행 삭제(테이블 비대화 방지) |
| `closing_bet` | 평일 08:30~20시(30분) | Phase 1/2 스크리닝 → Phase 1 진입 전 **ETF/ETN 코드 기반 제외**(ka10099 mrkt_tp 8/60/70/90 상장 리스트 → `_excluded_codes`, 2026-07-10 — 이름 키워드 `EXCLUDE_KEYWORDS` 는 ARIRANG→PLUS 같은 리브랜딩에 뚫려 백업으로 강등, 로드 실패 시 키워드만으로 동작) → `daily_stock_report`(Phase 2 **유니버스 전체** 저장) + `trade_signal`(selected만 핸드오프, `rule_names` 태깅) 적재. 저장은 **분석 컬럼만 upsert**(탈락 종목만 삭제) — 다른 워커가 같은 날 행에 쓴 관측 컬럼(19:50 NXT 스냅샷 등)을 20:00 이후 재실행이 지우지 않는다(2026-07-09, 이전 DELETE+INSERT 는 매일 소실시킴). **분석 컬럼 목록은 `_analysis_row` 의 키에서 파생**한다(2026-07-28 구조 수정) — 예전엔 컬럼 목록(`_ANALYSIS_COLS`)과 값 dict 를 나란히 나열해서, `disc_*` 3종을 목록에만 추가하고 값 dict 를 빠뜨린 실수로 7/28 하루치 리포트(13회 실행 전부)가 유실됐다. 이제 컬럼 추가는 한 곳(값 dict)만 고치면 INSERT/UPDATE 문이 따라오므로 두 목록이 어긋날 수 없다. 남은 문자열 참조인 upsert 정책 집합(`_FIRST_WRITE_WINS`/`_PRESERVE_ON_NULL`)은 분석 컬럼에 없는 이름이 있으면 raise(오타·리네임으로 정책이 조용히 무력화되는 것 방지). 그 밖의 저장 실패(DB 장애·타입 오류 등)는 **관리자 텔레그램 경보**(`send_report_save_alert`) — 저장 예외는 후속 단계(핸드오프 등)를 막지 않도록 삼켜지므로 경보 없이는 로그를 직접 볼 때까지 리포트가 빈 채로 방치된다. Phase 2는 음전 후보도 정밀분석·저장해 rule_evaluator 연구 표본으로 쓰고, 실제 selected/핸드오프만 선정 레이어에서 음전 제외한다(2026-07-07). 정배열/신고가는 가점으로만 반영(2026-07-03 풀 확대). **선정 레이어**(`edge_selection`, `EDGE_SELECTION_MODE` 코드 기본 `legacy`=음전 제외 후 점수 top-N, **운영은 `.env` 로 `hybrid`**)가 `selected`/핸드오프만 정하고 점수·rank_no·저장은 불변. `hybrid` 는 live selector rule 매칭 종목을 **점수 순위와 무관하게** 우선 슬롯에 넣고 남은 자리만 점수순으로 채운다 — 그래서 매수 목록에 점수 하위 종목이 들어온다(실측 2026-07-29: 기아 35위·신한지주 62위, `f5_prog_persistent`). 그 근거는 `trade_signal.rule_names` 뿐 아니라 **`daily_stock_report.rule_names`**(sql/43, 2026-07-29)에도 태깅해 종목 탭·리포트 화면이 '룰 선정' 배지와 실제 점수 순위를 보여준다 — 예전엔 근거가 trading DB 에만 있어 점수 62위 종목이 표시 순번상 "10위"로 읽혔다. `selected` 와 같은 루프에서 정하고 매 실행 덮어쓴다(legacy 폴백의 NULL 이 정상 — 그 실행은 실제로 점수순 선정이었다). veto rule 은 전 모드에서 선정 직전 제외 — 바이오 veto 는 2026-07-10 HLB 하한가 사건으로 도입: `veto_bio`(전면 제외, sql/16)와 `veto_bio_kosdaq`(코스닥 바이오만, sql/17)를 candidate 로 병행 채점해 비교한 결과 **`veto_bio_kosdaq` 만 live**(2026-07-27 승격), 상위집합인 `veto_bio` 는 **retired**(2026-07-28 — 코스닥판이 live 라 증분이 코스피 바이오 n=4·3거래일뿐이고 그 증분 대체효과가 -0.80%p 로 오히려 손해 방향). 판별 컬럼은 선정 시점 파생 `is_bio`(edge_features)·`market`(ka10100 캡처). **공시 veto**(2026-07-28): 선정 시점에 `stock_event`(DART) 를 벌크 조회해 `disc_count`/`disc_bad_type`/`disc_good_type` 을 굽고, live rule `veto_disclosure_severe`(sql/38 — 선행 `veto_disclosure_bad`(sql/37)는 retired)가 `disc_bad_type` 을 보고 제외한다 — 30분마다 재실행되는 구조 덕에 **저녁 재실행(19:00)에는 장 마감 후 공시(15:30~18:00)까지 반영**되고, 제외된 종목의 잔여 pending 시그널은 `push_trade_signals` 가 `expired` 로 정리해 19:30 NXT 매수에서 자동 탈락한다(trading 자금 경로 무변경). KRX 15:20 에 이미 체결된 분은 되돌릴 수 없어 익일 아침 `news_guard` 담당 |
| `gap_check` (`--base-krx`/`--base-nxt`/`--check-nxt`/`--label-nxt`/`--check-krx`) | 평일 15:20 / 19:50 / 08:03 / 08:06 / 09:03 | 실매매 청산 창과 동일 기준의 갭 측정. 15:20 KRX(top-10)·19:50 NXT 기준가를 state 로 수집(19:50 NXT 조회되는 종목=NXT 종목) → 익일 08:03 NXT 종목(`gap_nxt_*`), 09:03 KRX 종목(`gap_krx_*`) 확정 — 종목별로 자기 venue 창 하나만 채점. 기준가 미수집 시 리포트가 폴백(알림에 ≈ 표시). 텔레그램 알림은 09:03 확정 후 하루 1회. **19:50(`--base-nxt`)은 확장 관측**: 유니버스 전체에 KRX 확정 종가+NXT 현재가(종목당 2콜)를 붙여 `daily_stock_report` NXT 스냅샷(`krx_close_price`·`nxt_price_1950`·`nxt_gap_pct`·`nxt_after_value`·`nxt_listed`) UPDATE + `market_snapshot` 1행 upsert. **08:06(`--label-nxt`)은 엣지 연구 라벨**: 전일 유니버스 전체 NXT 상장 종목의 08:06 NXT 가격 → `nxt_open_price`·`nxt_open_ret`(앵커=KRX 확정 종가) UPDATE — 실매매 08:03(settle·check-nxt, top-10)과 시각·부하 완전 분리. 관측 확장은 매매 영향 0 |
| ⏰ `outcome_backfill` | 평일 09:30 | `daily_stock_report` 유니버스 전체에 **일봉 결과 라벨 4종**(`next_open_ret`·`next_high_ret`·`next_low_ret`·`next_close_ret` = 리포트일 종가→다음 거래일 시가/고가/저가/종가 등락률) + **실집행 통합 라벨**(`exec_leg_ret`·`exec_leg_venue`) 백필. `exec_leg_ret` 는 종목별 실제 청산 venue 기준(NXT: 전일 19:50→익일 08:03, KRX: 전일 15:20→익일 09:03)을 하나로 접은 evaluator 기본 라벨. 일봉은 같은 일봉 1회 조회에서 파생, 실집행 레그는 1분봉 첫 체결가 기준. ±35% 초과 아티팩트 스킵, 미완결분은 다음 실행에서 재시도. 실집행 레그는 `exec_leg_ret` 활성 rule 의 가장 이른 registered_at 이후만 대상(활성 rule 이 없으면 **건너뜀** — 과거 전체 분봉 백필 폭주 방지), NXT 시도 후 KRX 폴백 시 로그 기록. **후속 재료 채점**(2026-07-29~): `news_durability` 라벨이 있는 과거 행에 `news_followup_days`(리포트일 +1~+`NEWS_FOLLOWUP_WINDOW_DAYS`(10)일 중 **시세보도 어휘를 뺀** 언급이 있던 날짜 수)를 채운다 — 지속성 라벨이 맞았는지 재는 유일한 사후 값. DB·순수 로직만이라 **키움 API 콜 0**이고 일봉 백필 대상이 없어도(토큰이 없어도) 돌며, 실패해도 가격 라벨 백필을 막지 않는다. 시세보도를 빼는 이유는 역인과(갭상승이 "XX 급등" 기사를 만든다 — 실측 21%)이고, 이진(있음/없음) 대신 일수를 세는 이유는 10일 창이면 대형주가 거의 100% '있음'이라 이진 라벨이 또 시총 더미가 되기 때문. 창이 열린 동안 매 실행 재계산(멱등·단조 증가), `news_mention` 보존 14일이라 창+지연이 14일을 넘으면 앞쪽이 잘린다 |
| ⏰ `after_hours_labels` | 평일 17:50 | 당일 유니버스 전체에 **시간외 반응 + 리스크 라벨** UPDATE(관측 컬럼 — closing_bet upsert 와 분리, 점수·매매 무영향). ① 시간외단일가 `ah_price`·`ah_flu_rt`·`ah_volume`(ka10087 — 세션 16~18시 **중**에만 값이 살아있어 17:50 스냅샷, 체결 0주는 NULL) + `ah_react`(시간외가 ÷ 당일 KRX 종가 −1%, 앵커=수정주가 일봉 — predicate 가 컬럼 간 비교를 못 해 파생으로 굽는 rule 용 컬럼) — 익일 갭 선행지표 ② 리스크 지표(악재 veto 연구, 전부 **T-1 확정치**라 선정 시점에 알 수 있던 값=누수 없음): `credit_remn_rt`(ka10013 신용 잔고율)·`short_wght`/`_5d`(ka10014 공매도 비중)·`lend_remn`/`lend_irds_5d`(ka20068 대차 잔고·5일 증감 합) ③ `exec_str`/`_5d`(ka10047 체결강도, KRX 마감 후 확정치) ④ `market_snapshot.ah_up3_cnt`/`ah_dn3_cnt`(ka10098 시간외 ±3% 급등/급락 종목 수 — 시장 분위기). 스냅샷 TR 특성상 과거 백필 불가 — 놓친 날은 NULL |
| ⏰ `rule_evaluator` | 평일 09:40 | **Edge Ledger 일별 채점(2-pass)** — pass1: **retired 포함 전 rule**(2026-07-31 사용자 결정 — retire 는 '판정 종결·알림/게이트 제외'이고 관측은 계속한다. 채점을 끊으면 종료된 가설의 성적이 그 시점에 얼어붙어 "그때 폐기한 게 옳았나"를 나중에 못 따진다. 게이트 분기가 candidate/live 만 타므로 알림·승격·강등에는 올라오지 않고, 실매매는 `status='live'` 조회만 하므로 개입도 없다)을 유니버스 전체 + `market_snapshot` 에 적용(`edge_predicate.evaluate`), `exit_label` 결과 수집 → `mean_net = 평균 − EDGE_COST_PCT` → `edge_rule_daily` upsert(catch-up: 라벨 미도래 날짜는 다음날 재시도, 14일 초과 시 n=0 sentinel 종결 — 실시간 라벨은 소급 불가라 영구 재시도 방지) + registered_at 이후 표본만으로 누적 stats 재계산(`n_days`=라벨 표본이 있는 거래일 수, `mean_net_days`=일 등가중 평균(매칭 많은 날 쏠림을 드러냄 — f4 사례 종목-일 가중 +1.19% vs 일 등가중 +0.45%), `t_days`=거래일을 관측 단위로 묶은 t(거래일 1일이면 None), `recent_mean_net_days`=최근 창 일 등가중(진단값) 포함. **화면용 게이트 상태**(2026-07-28): `promo_eligible`·`promo_blockers`(막고 있는 항목의 짧은 라벨 — 사유 문자열의 콜론 앞부분이라 문구 변경 시 자동 동기화)·`promo_policy`(적용 정책 — 상태 무관 전 rule 에 기록해야 후보 0종일 때도 화면에 표시된다)·`decision_stage`. 프론트가 `min_sample` 로 진행률을 재추정하다 그 조건이 게이트에서 빠지자 **'진행바는 꽉 찼는데 검증 중'** 불일치가 생긴 뒤, 조건 판정은 서버만 하고 화면은 이 값들을 렌더링만 하도록 정리했다(프론트 진행바는 거래일 축적만 표시). **초과 계열**(2026-07-28, `n_exc`·`mean_exc`·`ci_low_exc`·`mean_exc_days`·`t_days_exc`): 그날 **유니버스 자기제외 평균**(`get_universe_label_totals` 의 날짜별 합계·개수에서 그 rule 매칭 종목을 뺀 나머지)을 기준선으로 한 초과분 — selector 승격의 통계 게이트가 이걸 본다. 자기제외인 이유: 대조군(=selected top10)을 기준선으로 쓰면 rule 매칭 종목이 평균 54%(일부 100%) 그 안에 있어 **자기 자신을 빼는** 편향이 생긴다(분산이 기계적으로 줄어 잡음 감소처럼 보이지만 초과분을 0 쪽으로 누른다). 실측 잡음 감소 26%=필요 거래일 1.8배 단축. 비용(EDGE_COST_PCT)은 초과분에서 상쇄되므로 원시 계열에만 적용. 매칭이 유니버스 전체인 날은 기준선이 없어 초과 표본에서 제외). 채점 당시 미도래였던 `next_low_ret` 는 재시도 마감 전 날짜에 한해 matched 스냅샷에 소급 반영(worst_low_ret 복원 — exec_leg_ret 는 D+1, next_low_ret 는 D+2 에 채워지는 시차 보정). pass2: 전 rule stats 가 신선해진 뒤 `edge_policy.check_promotion`(라우터와 동일 게이트: selector 는 min_sample + **PROMO_MIN_DAYS=10 거래일** + **ci_low_exc>0** + **t_days_exc≥1.65**(초과 계열) + live 대조군 우위(원시) — 종목-일 n 은 같은 날 시장 무브로 상관되어 거래일 수가 실효 표본, veto 는 n_days≥10 + 제외 종목 mean_net<0 실익 게이트)으로 `stats.promo_eligible`·`stats.decision_stage` 저장. **게이트 판정은 판정 일정(sql/39)에 따라 발견·확인 시점에만 실행**되고 그 결과를 `decision` 에 기록한다 → 텔레그램 알림 3종 — 승격 후보(확인창 확증 완료) / 집행 설계 필요(통계·표본 충족이나 선정 시점 실행 불가 피처)는 **판정일에만** 오지만, **강등 검토는 판정 일정 밖이라 매 평일 재검사**되어 조건이 유지되는 동안 반복된다(2026-07-29 푸터 문구를 섹션별로 분리 — 예전엔 '판정일에만' 한 줄이 강등에도 붙어 오해를 샀다). 강등 검토(`edge_policy.check_demotion` — live 비대조군, **최근 10거래일 창** n≥20·거래일≥5 + **역할별 부호**: selector 는 매수 종목 mean_net<0, veto 는 제외 종목 mean_net>0 — 종목-일 30개 창은 광역 rule 에서 거래일 3일이라 하루 시장 무브가 오탐을 냈고(2026-07-20), 부호를 역할 간 공유한 것도 오탐이었다(2026-07-28), benchmark 는 강등 시 승격 게이트가 fail-closed 로 막혀 감시 제외). **강등 알림은 게이트가 본 `recent_mean_net`(종목-일) 옆에 `recent_mean_net_days`(일 등가중)를 병기**하고 **부호가 갈리면 ⚠️쏠림**을 표시한다(2026-07-29 — 게이트 조건은 그대로, 판단 재료만 노출. 실례 veto_bio_kosdaq: +0.18%(종목-일) vs -0.20%(일 등가중), 상위 3건을 빼면 -0.70% 라 강등 근거가 아니었다). 전이는 관리자 API 수동, 매매 집행 없음 |
| ⏰ `weight_tuner` | 토 08:00 | 지난주 실현손익(단 `SCORE_LOGIC_MIN_DATE`=2026-07-07 이전 구 로직 주는 스킵) → GPT 가중치 제안 → backtest 검증: IMPROVES=pending(승인 대상) / 그 외=archived(비적용·표시용) + [건강지표] 로깅 |
| ⏰ `macro_event_check` | 월 08:20 | `macro_event`(거시 이벤트 캘린더 — trading macro_gate 가 보유 창의 FOMC·CPI·고용 이벤트로 시드 축소, `sql/18. migrate_macro_event.sql` 수동 시드) 고갈 감시 — 마지막 이벤트가 3주 내면 exit 1 → 텔레그램 경보(시드 잊으면 게이트가 '이벤트 없음'으로 조용히 무력화되는 것 방지). 연말마다 다음 해 일정 시드 필요 |
| `kis_night_futures_ws` | 평일 18:00~익일 새벽 | KIS WebSocket 야간선물 체결 → `kis_night_future` |
| (토큰) `kis_token_refresh` | 매일 07:00 | 키움+KIS 토큰 갱신(`refresh_tokens.sh`) |

---

## 핵심 도메인 흐름

```
콘텐츠 수집(youtube/telegram) ──► content_analysis (sentiment, 한줄요약 tldr, 테마 tags, 종목별 방향 stock_calls)
뉴스 속보 채널(고빈도) ──사전매칭(LLM X)──► news_mention (종목·헤드라인, 원자료·14일)
                                        │ ├► 익일 07:00~09:25 news_guard ─► 보유 종목(trading.position) 밤사이 중대 악재 OpenAI 판정
                                        │ │    → news_veto_verdict(severe=1) ─► trading monitor 가 개장 즉시 전량 매도(뉴스 베토)
                                        │ └► 선정 시점(closing_bet) 뉴스 보유 전건 5일치 헤드라인 ─► OpenAI 벌크 재료 판정
                                        │      → daily_stock_report.news_durability(연속/중립/소진) + 사실 4축 (점수 무영향)
                                        │      → 익일 +1~+10일 후속 재료 실현 일수로 라벨 채점(outcome_backfill)
                                        │
DART 전자공시(30분 폴링) ──룰 분류(LLM X)──► stock_event (사건 계층: 종목×사건 1행, 영구 보존)
                                        │ └► 선정 시점 집계 → disc_bad_type ─► veto_disclosure_bad(live)가 후보 제외
                                        │      · 15:30~18:00 장 마감 후 공시가 19:00 재실행에 반영 → pending 시그널 expired
                                        │        → 19:30 NXT 매수 자동 취소(자금 경로 무변경)
                                        │
종가 분석(closing_bet, 평일 13:00~15:00)│
  Phase 1 거래대금(양시장 통합 ka10032 mrkt_tp=000, 1페이지 100행 → TOP_N_BY_VALUE 윈도우) + 관심섹터 보강 · ETF/ETN 코드셋 제외(ka10099, 2026-07-10) · 공통 기본필터(제외키워드·시총·거래대금) ─┘
        │  · 2026-07-28 시장별 분리(001/101 각 50) → 통합 순위 전환: 분리 방식은 시장 규모 차이를 무시하고
        │    각 50 슬롯을 배분해 코스닥 중소형을 과대 대표했다(개별 75건 중 코스닥 50건 / 유니버스 32%).
        │    통합 전환 후 코스피 38·코스닥 7(16%), 후보 45건. 거래대금 하한은 순위 응답만으로 판정되므로
        │    시총(ka10001) 조회 **전에** 컷한다(하한 미달 종목의 무의미한 개별 조회 방지).
        │  · 실질 컷은 TOP_N 이 아니라 `MIN_TRADING_VALUE` 다 — 7/28 실측 78행에서 하한(1,000억) 도달,
        │    100행 끝은 784억이라 1페이지로 충분(연속조회 불필요). 다만 여유가 22행뿐이라 활황장엔
        │    100행이 하한 위에서 끝나 유니버스가 조용히 잘릴 수 있다 → 마지막 행이 하한 이상이면
        │    **경고 로그**를 남긴다(ka10032 는 연속조회 지원, 경고가 뜨면 max_pages 상향).
  Phase 2 음전 포함 정밀분석(연구 표본) → 수급(기관/외인/개인/프로그램)+정배열/신고가+대장주+테마+콘텐츠+뉴스+등락률 점수
  종합점수 = 수급 + 정배열 + 신고가 + 대장주 + 테마(거래대금 하한 통과 유동성 상위권 교집합만) + 콘텐츠 + 뉴스 + 등락률(2~12% 가점 / 15%+ 감점) (가중치 튜닝 대상)
        │  · 뉴스 재료: news_count 집계 + 뉴스 있는 전건 벌크 LLM 판정 → daily_stock_report 표시
        │    (SCORE_NEWS_BONUS 기본 0 → 현재 점수 무영향, 주간 튜너가 성과 따라 상향 가능)
        │  · 뉴스 연구 라벨(2026-07-03~, 점수 무영향 — next_open_ret 조인 엣지 검증용):
        │    집계 — news_unique_count(헤드라인 dedup 고유 기사) · news_pm_count(12시 이후 신선도) ·
        │           news_first_today(14일 내 첫 등장) · news_prior_avg(직전 7일 일평균, 서프라이즈 분모)
        │    LLM — news_sentiment(방향 0~100) · news_catalyst(재료 유형) ·
        │           **재료 지속성**(2026-07-29~): news_next_milestone · news_amount_locked ·
        │           news_driver_scope · news_stage → 파생 등급 news_durability(연속/중립/소진) +
        │           판정 근거 news_label_reason (상세는 core/news_material_judge.py 절)
        │      ✅ 커버리지: 예전엔 하루 최대 5종목(Ollama 처리량, 유니버스의 ~8% — 4주간 46행/12거래일로
        │         검증 불가였다). 2026-07-29 OpenAI 벌크 판정으로 **뉴스 있는 전건**(≈16행/일)으로 확대.
        │         ⚠️ 그래서 `veto_bad_news`(live, news_sentiment<=30)의 실효 커버리지도 함께 넓어졌다 —
        │            rule 의 설계 의도대로지만 표본 성질이 이 날부터 달라진다(승격·강등 판정 시 유의).
        │      · 30분 재실행 대비 캐시: 새 헤드라인이 없으면(news_judge_max_at ≥ 오늘 마지막 언급 시각)
        │        LLM 재호출 없이 기존 라벨을 메모리 dict 로 캐리포워드한다 — rule 평가가 메모리 행을
        │        보므로 캐리포워드가 없으면 스킵한 실행에서 veto 판단이 달라진다. DB 백스톱은
        │        stock_report._PRESERVE_ON_NULL(판정 스킵·LLM 실패의 NULL 이 그날 판정을 지우지 않음).
        │      · 채점: news_followup_days(outcome_backfill) — 리포트일 +1~+10일 중 **시세보도 제외**
        │        언급이 있던 날짜 수. 지속성 라벨이 맞았는지 재는 유일한 사후 값이다.
        │        ⚠️ 일수로 세도 시총 부하는 남는다(7/20 실측 현대차·SK하이닉스 9일 vs 소형주 0일)
        │           → **라벨 채점 전용**. 종목 간 비교는 news_prior_avg(자기 기저)나 시총 버킷 대비로
        │           정규화하고, 수익 채점(next_open_ret)과 섞지 말 것(처방이 정반대다).
        │      · 같은 날 여러 번 판정되면 **마지막 판정이 남는다** — 재료가 섞인 종목은 어느 재료를
        │        고르는지가 실행마다 달라질 수 있다(실측: SK하이닉스 실적↔반도체 빅딜). 저장 값은
        │        저녁 실행분이므로 '장 마감 후 확정 재료'라는 의도와는 맞는다.
        │  · 공시 사건 라벨(2026-07-28~, stock_event 집계 — disc_bad_type 만 veto 참조, 나머지 점수 무영향):
        │    disc_count(당일 공시 건수) · disc_bad_type(최우선 악재 타입, 정정 제외) · disc_good_type(대표 호재 타입)
        ├─► daily_stock_report — Phase 2 유니버스 전체 저장(selected=1=핸드오프, 0=비선정/음전 연구 후보)
        │     · 기본 조회(대시보드·gap_check)는 selected=1 만; 연구는 include_unselected=True 로 전체
        │     · rule_names(sql/43) — selected 와 한 몸으로 매 실행 재판정되는 선정 근거 태그.
        │       hybrid/rules 모드에서 이 종목을 뽑은 live selector rule name 콤마 목록, 점수순 선정·비선정은 NULL.
        │       hybrid 는 점수 순위와 무관하게 매칭 종목을 넣으므로(실측 7/29 기아 35위·신한지주 62위) 이 태그
        │       없이는 화면이 '점수로 뽑힌 종목'처럼 보인다 → 카드는 '룰 선정' 배지 + 실제 점수 순위를 함께 낸다.
        │     · 저장 시점 파생(API 콜 없음, F4의 눈): sector_rel_ret(등락률−동일섹터 평균)·sector_leader_chg(동일섹터 최고 등락률)
        │     · F5 수급 구조·테마 피처(2026-07-05~, 점수 무영향 — 전부 선정 시점 수집이라 live 자격):
        │       기수집 응답 캡처 — foreign_brokers_buying(ka10002 외국계 창구 2곳+) · prog_buy_days(ka90013 5일 중 순매수일) ·
        │                        afternoon_ret(ka10080 13시 시가→현재가) · theme_strength(ka90001 소속 테마 당일 등락 최대) ·
        │                        frgn_exhaust_rate(ka10001 for_exh_rt)
        │       추가 1콜 — vol_ratio(ka10081 당일 거래량÷20일 평균) / DB 파생 — first_seen(직전 14일 유니버스 부재) ·
        │                  frgn_exhaust_chg(직전 리포트 거래일 대비 소진율 %p, repository.get_prev_frgn_exhaust_map)
        │     · 차트 구조 피처(2026-07-19, sql/20·21): dist_prior_high_pct(ka10081 같은 1콜 재사용 — 250일 전고점(고가, 당일 제외) 대비 거리 %) ·
        │       round_dist_pct(현재가 파생 — 최근접 라운드피겨 1·2·5×10^k원 대비 거리 %) · ma5_reclaim(전일 5일선 아래 → 당일 5일선 위 양봉 재탈환).
        │       매물벽 음의 가설 veto_prior_high_wall·veto_round_figure_cap + 돌파 대칭 쌍 f5_prior_high_break·f5_round_figure_break(sql/22) + 눌림목 반등 f5_ma5_reclaim(전부 candidate)이 참조
        │     · 외인 서지 축 피처(2026-07-19, sql/23·24 — 종가베팅 팁 PDF "수급 1음봉/2음봉" 통설 검증): days_since_frgn_surge(supply_history 파생 —
        │       직전 거래일 중 외인 순매수≥100억 서지의 경과 거래일, 당일 제외) · red_candle(ka10081 같은 1콜 재사용 — 당일 음봉 여부) ·
        │       red_candle_streak(같은 1콜 — 당일 포함 연속 음봉 수). 눌림 f5_frgn_surge_pullback1(수급 1음봉)·f5_frgn_surge_pullback2(수급 2음봉,
        │       연속 음봉만) + 지속 f5_frgn_surge_carry(전부 selector candidate)가 참조. 음봉 매칭 표본 대부분이 음전이라 live 승격돼도
        │       실효 집행은 음봉+양전(갭업 후 밀림)에 한정됨을 승격 판단 시 감안
        │     · 매물대 프로파일 피처(2026-07-19, sql/25 — 매물대 PDF 후속, ka10081 같은 1콜 재사용): overhead_vol_ratio(250일 거래량 중 현재가 위
        │       비중 — 두터움) · poc_dist_pct(최대 거래 집중가 POC 거리 %). rule 은 의도적으로 미등록 — 같은 레벨 축 rule 5종의 8월 판정 후
        │       '두터움' 조건부 결합으로 등록(표본은 지금부터 선축적)
        │     · 수급매매 용어 rule 3종(2026-07-19, sql/27~29 — 신규 피처 0, 기존 컬럼 조합): 수급 미사일(first_seen+동반매수+시총<=2조+바닥권,
        │       저빈도) · 수급 독수리(서지 3~4일+횡보 — 서지 경과 축 완성) · 수급 변곡점(supply_days==1+vol_ratio>=2+양전). 전부 selector candidate
        │     · 프로그램 오전/오후 분해(2026-07-19, sql/26 — ka90008 신규 엔드포인트, 후보당 1페이지 스냅샷): 정오 창(12:00~12:45) 실행이
        │       현재 누적을 prog_am_net 으로 저장(repository first-write-wins) → 오후 창(12:45~15:35) 실행이 prog_pm_net=현재−정오 차분
        │       (틱 워킹은 유동 종목 50페이지+ 라 기각, 실측). 창 밖 실행 스킵(키움 최근 거래일 폴백 오염 방지) + NULL 보존 upsert.
        │       f5_prog_pm_reversal(selector candidate — 오전 매도→오후 전환, 사전 점검 불가·순수 out-of-sample)이 참조
        │     · 재무 스냅샷(2026-07-22, sql/32 — ka10001 같은 응답 재사용, 추가 콜 0, 점수 무영향): edge_features.financials 가
        │       fin_per·fin_pbr·fin_ev(밸류에이션 배) · fin_roe(%) · fin_eps·fin_bps(원) · fin_sales·fin_op_profit·fin_net_income(억원) 파싱.
        │       분기 저속 데이터라 매일 중복 저장(연구용 무해), 부채비율은 ka10001 미제공이라 제외. 선정 시점 컬럼이라 SELECTION_TIME_COLS 포함.
        │       파생 op_earnings_yield(2026-07-22, sql/34 — edge_features.op_earnings_yield=영업이익÷시총)로 "영업이익이 시총 1/10은 돼야"(≥0.1)
        │       통설을 f8_op_earnings_yield(f8_value/selector candidate, sql/35)로 등록 — predicate 가 컬럼-상수만 되어 비율을 선정 시점에 미리 구움.
        │       나머지 재무 축(밸류에이션·수익성)은 표본 축적 후 판정해 등록(veto 적자·극단 고PER 등)
        │     · 호가 미시구조 스냅샷(2026-07-22, sql/33 — ka10004 신규 엔드포인트, 후보당 1콜): edge_features.order_book_features 가
        │       ob_imbalance(총매수÷총매도잔량, >1 매수우위) · ob_fpr_imbalance(최우선 잔량비) · ob_spread_pct(스프레드/현재가 %) 파생.
        │       연속장 중만 유효 — 장 종료 후 잔량 0→None, repository 가 PRESERVE_ON_NULL 로 종가 직전 마지막 세션 스냅샷 보존(매수=종가라 ~15시가 근사).
        │       rule 미등록(데이터부터 축적) — 호가 불균형이 오버나이트 라벨을 예측하는지 표본 축적 후 판정. SELECTION_TIME_COLS 포함(향후 live 자격)
        │     · 선정 레이어(edge_selection, EDGE_SELECTION_MODE): 음전 후보는 연구 표본으로 저장하되 핸드오프에서 제외. legacy=점수 top-N(기본) / hybrid=live rule 우선+점수 채움 / rules=live rule 합집합(매칭0=무거래). veto 는 전 모드 선정 직전 제외. live rule 로드 실패 시 모드 자체를 legacy 로 폴백(로그 명시) — 빈 rule 목록으로 rules 를 돌려 무거래가 되는 사고 방지
        └─► trade_signal (status=pending, selected만, rule_names 귀속)  ─► trading 도메인이 집행(도메인 로직 무변경, rule_names 는 안 읽음)
당일 15:20 gap_check --base-krx ─► top-10 KRX 기준가(state) · 다음날 08:03/09:03 --check-* ─► daily_stock_report.gap_*(top-10) 갱신(NXT: 19:50→08:03, KRX: 15:20→09:03)
당일 17:50 after_hours_labels ─► 유니버스 전체 시간외단일가(ah_*, 익일 갭 선행지표) + 리스크 라벨(credit_remn_rt·short_wght/_5d·lend_remn/lend_irds_5d — T-1 확정치, 악재 veto 연구) + 체결강도(exec_str/_5d) UPDATE + market_snapshot 시간외 breadth(ah_up3_cnt/ah_dn3_cnt)
당일 19:50 gap_check --base-nxt ─► top-10 NXT 기준가(state, 갭 체크용) + 유니버스 전체 NXT 스냅샷(daily_stock_report.krx_close_price·nxt_*) + market_snapshot 1행(지수·선물·VIX·환율)
다음날 08:06 gap_check --label-nxt ─► 유니버스 전체 NXT 상장 종목 nxt_open_price·nxt_open_ret(앵커=KRX 확정 종가) — 실매매 08:03 경로와 분리된 청산창 연구 라벨
  └► F1~F4 가설이 볼 수 있는 관측을 15:00 KRX 시점 너머(19:50 애프터마켓·시장 레벨·08:06 프리마켓)로 확장 — 순수 기록 레이어(매매 영향 0)
평일 09:30 outcome_backfill ─► daily_stock_report 일봉 결과 라벨 4종(유니버스 전체, 리포트일 종가→다음 거래일 시가/고가/저가/종가 등락률, 같은 일봉 1회 조회 파생) + 실집행 통합 라벨 `exec_leg_ret`/`exec_leg_venue`(NXT: 19:50→08:03, KRX: 15:20→09:03, 1분봉 첫 체결가)
  └► 선정/비선정을 가르는 요인 + rule 별 최적 청산창(시가/고저/종가·08:06 프리마켓·실집행 venue)을 사후 측정하기 위한 균일 결과 라벨(비선정 후보의 반사실 포함)
평일 09:40 rule_evaluator ─► 전 가설(edge_rule, retired 포함 — 관측 계속)을 유니버스+market_snapshot 에 매일 적용 → `exit_label`(기본 `exec_leg_ret`)로 edge_rule_daily(페이퍼 성적) 누적 → 누적 stats·승격/강등 알림
  └► 학습 루프의 심장. candidate 로 등록→매일 자동 채점→표본·신뢰구간 충족 시 관리자 API 로만 live 승격(자동 승격 없음). 집행 연결은 Phase 4
  └► 초기 카탈로그는 sql/8. seed_edge_rules.sql 로 시드(control_legacy_top10=live 기준선 · F1~F4 candidate · veto_bad_news live · veto_overheat_gap candidate — 19:50 피처(nxt_gap_pct)라 선정 시점 실행 불가, edge_policy 게이트가 승격 차단). 인과 근거·registered_at(표본 시작일) 포함, INSERT IGNORE 라 재실행해도 등록일 보존
  └► f9_disc 공시 rule 은 **확실성에 따라 둘로 갈라 등록**(sql/38, 2026-07-28). `veto_disclosure_severe`(**live**): 존속위험·불성실공시·횡령배임·계약해지 — 통설이 아니라 확정 사실이고 reduce-only 라 오차의 최악이 기회비용이다. `veto_disclosure_dilution`(**candidate**): 희석 계열 — 같은 날 첫 실수집이 "희석=악재" 통설을 반증했다(유상증자 8건 전부 제3자배정, NAVER→NVIDIA 건은 상승). 실매매 미개입 상태로 rule_evaluator 가 "제외했으면 이득이었나"를 매일 채점하고, veto 게이트(n_days≥10 + mean_net<0) 통과 시 관리자 승인으로 승격한다. **선행 시도였던 `veto_disclosure_bad`(sql/37)는 retired** — 사전등록 원칙상 predicate 를 조용히 좁히지 않고 새 rule 로 재등록했다(원장에 '무엇을 시도했고 왜 좁혔는지'가 남는다). live 쪽도 제외 종목 평균(mean_net)이 **양수로 쌓이면 = 우리가 손해 보는 중**이니 강등을 검토한다
  └► 시간외·리스크 가설은 sql/14. seed_after_hours_rules.sql 로 시드(2026-07-09, id 27~31: f6_ah_react_up·veto_ah_react_down·veto_short_surge·veto_credit_high·f5_exec_str_strong — 전부 candidate, 17:50 수집 컬럼이라 선정 시점 실행 불가=페이퍼 전용, 임계값은 7/9 유니버스 p90 실측으로 사전 등록). family `f6_ah` 는 edge_policy FAMILIES 에 등록
  └► 바이오 veto 는 sql/16(veto_bio 전면 제외) + sql/17(veto_bio_kosdaq 코스닥만)로 시드(2026-07-10 HLB FDA CRL 하한가 사건, family `f7_risk`, role=veto). 시총 컷은 기각 — HLB 가 시총 7조 코스닥 대형주라 '중소형' 기준으론 사건을 못 막는다(실측). **판정 완료**: 페이퍼 성적(전면 vs 코스닥만)을 비교해 `veto_bio_kosdaq` 만 **live**(2026-07-27 승격 — 근거는 평균 엣지가 아니라 하한가 꼬리 차단: HLB -30.4%·로킷 -14.5%·온코닉 -14.3% 급 꼬리가 대체 후보 쪽엔 없다), 상위집합 `veto_bio` 는 **retired**(2026-07-28 — 코스닥판이 live 인 이상 증분은 코스피 바이오뿐이고 n=4·3거래일에 대체효과 -0.80%p(t=-0.48)로 손해 방향. 삼바·셀트리온은 하한가 리스크가 없어 전면 제외의 근거가 없다). **겹치는 veto 주의**: 상위/하위집합 veto 가 공존하면 게이트 stats 가 이미 live 인 쪽 표본을 그대로 포함해 승격 후보로 계속 뜬다 — 승격 검토 시 predicate 차집합으로 증분만 따로 재야 한다 |
  └► live 승격 규율(edge_policy 단일 소스): selector 는 n≥min_sample·**초과 CI하한>0**·**초과 일 클러스터 t≥1.65**(2026-07-28 추가 — 유니버스 자기제외 기준)·live 대조군 우위(원시 mean_net, 부재 시 fail-closed)·선정 시점 실행 가능성 전부 충족 + 월 2개 상한 + 관리자 승인. veto 는 reduce-only 라 CI·대조군·일 클러스터 t 는 면제하되(가치가 평균이 아니라 꼬리 차단) 최소 실익 게이트(n_days≥10 + 제외 종목 mean_net<0, 2026-07-13)·실행 가능성 충족. benchmark(대조군·수급 밴드) 는 전 게이트 면제지만 실전 투입 알림/화면 대상에서 제외(기준선 교체는 API 로 수동). 19:50/익일 피처 rule 은 페이퍼 검증 전용 — 집행 설계(선정 시점 이동) 변경 후 재검토
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
