# KRX 매수 시점 이동 — 15:20 종가 → 시간외단일가 마감(18:00) (2026-08-13)

> 상태: **설계만 완료 · 코드 변경 없음 · 사용자 승인 대기.**
> 대상은 **NXT 미상장(KRX 전용) 종목의 매수 창**뿐이다. NXT 경로(19:30~19:50)와 청산 경로
> (08:03/09:03/09:28)는 **전부 불변**이다. 자금 경로 변경이라 착수 전 승인이 필요하다
> (`AGENTS.md` 가드레일 — `trading/core/execution_engine.py` 편집 포함).

---

## 0. 한 줄 결론

| 항목 | 현행 | 변경안 |
|---|---|---|
| 매수 창 | 15:00~15:20 (KRX 종가 동시호가) | **17:50~17:56 주문 → 18:00 시간외단일가 체결** |
| 사용 신호 | 15:00 closing_bet 회차 | **17:30 closing_bet 회차** |
| 주문 유형 | 시장가(`trde_tp=3`) | **시간외단일가 지정가** (코드 미확인 → 선행 검증 필요) |
| 체결 확정 | 15:30 | 18:00 |
| 청산 | 익일 09:03 KRX 개장가 (settle `krx_open`) | **불변** |
| 영향 범위 | — | 전체 매수의 **약 25%** (90일 44건 / NXT 137건) |

바꾸는 이유는 진입가가 아니라 **정보 시점 정렬**이다. 선정·공시·시간외 반응이 전부 17:50까지
확정되는데 매수만 15:20에 홀로 앞서 있어서, 그 사이 정보를 하나도 못 쓴다.

---

## 1. 근거 (2026-08-13 실측)

측정 기간: 리포트 기반 2026-07-09~08-12 / audit 기반 최근 90일. 재현 쿼리는 §10.

### ① 선정 신선도 — 15:20에 산 종목의 48%가 그날 안에 톱10에서 빠진다

| | 건수 | `next_open_ret` | 승률 |
|---|---|---|---|
| 최종 톱10 유지 | 23 | +0.331% | 52% |
| 탈락(선정 해제 or rank>10) | **21 (48%)** | -0.160% | 50% |

차이 +0.49%p(각각 t<1). 근소 탈락만이 아니다 — 금호건설 rank 19, 대원전선 32, 빛과전자 38.

⚠️ 이 판정에 쓴 순위는 **20:30 최종값**이라 18:00 시점보다 정보가 많다(lookahead 편향).
`daily_stock_report` 가 upsert 라 회차별 순위가 남지 않는다 → §8 부수 작업으로 스냅샷 적재를 건다.

### ② `veto_ah_react_down` — 기각 사유가 "매수 창 시각"이었다

`docs/history/edge-ledger.md` 2026-07-31 판정:

> **ah_react 는 신호가 있으나 매수 경로가 구조적으로 없다** — 신호 종목은 NXT 미상장이므로
> 진입은 KRX 종가(15:20)뿐이고, 그 창이 수집(17:50)보다 **앞선다**.

즉 기각 사유가 신호 부재가 아니라 **오직 시각**이었고, 이 설계가 그 전제를 바꾼다. 현재 표본:

| 표본 | veto 대상 | 대상 평균 | 잔여 평균 | 대체효과 |
|---|---|---|---|---|
| selected (KRX 전용) | n=5 | -1.290% (승률 20%) | +2.063% (n=25) | **+3.353%p** (t=3.52) |
| 유니버스 전체 | n=26 | -0.947% (승률 23%) | +1.511% (n=187) | +2.458%p (t=2.15) |

`ah_react` 밴드 승률은 단조다 — ≤-1.5%: **29%** / [-1.5,-0.5): 57% / [-0.5,+0.5): 52% /
[+0.5,+1.5): 73% / ≥+1.5%: **88%** (n=203). `f6_ah_react_up`(≥+1.5%, 1만주+)도 n=15 평균
+3.985%·승률 87%로 selector 후보다.

⚠️ selected 표본 5건은 원장이 잡아둔 승격 조건(15건+)에 미달이다 → **2단계로 분리**(§8).

### ③ 진입가 — 부수 효과 (주된 근거 아님)

시간외단일가(17:50)는 KRX 종가 대비 평균 **-0.335%**(중앙 -0.198%, 양수 42%) — 할인이다.
진입만 옮긴 반사실은 +0.353%p/건(t=1.00), 일별 +0.502%p(t=1.15), 개선 17/31. **유의하지 않다.**
NXT 19:50이 +0.70% *프리미엄*(비싸게 삼)이었던 것과 부호가 반대인데, 얇은 단일가 판은 매도
우위라 할인이 붙는 구조로 보인다. 이 항목은 근거로 세우지 않고 관찰 대상으로만 둔다.

### ④ 유동성 — 병목이 아니다

우리 KRX 주문은 **중앙 13만원 / 최대 27만원**(90일 44건, 합계 552만원). 대상 종목의 시간외
거래대금은 중앙 13.8억 / 하위 10% 6.4억 / 최소 0.87억이다. 임팩트·부분체결 위험은 무시 가능하다.
다만 **시간외 체결 자체가 없는 종목이 9%**(31/34만 `ah_price` 보유) → 그날 매수 스킵이 된다(§7).

---

## 2. 현행 타임라인 (KRX 전용 종목)

```
15:00  closing_bet 회차            → trade_signal 갱신
15:00  trading-buy-krx 기동         (ecosystem.config.js:236)
       └ 15:12까지 신호 갱신 대기 → 시드 배분 → 수량 확정 → 15:20까지 하트비트
15:20  전 종목 시장가 매수 (KRX 동시호가)   signal_executor.py VENUES["krx"]
15:20  gap_check --base-krx 기준가 수집     (ecosystem.config.js:85)
15:30  종가 확정
15:31  fills_sync --venue krx  체결 반영 + 텔레그램
──────── 여기부터 정보가 들어오는데 매수는 이미 끝났다 ────────
15:30~18:00  장마감 공시(DART, :20/:50 수집) · 뉴스(:15/:45 수집)
16:00~18:00  시간외단일가 세션
17:30  closing_bet 회차             → 순위 재산출 (15:20 매수분의 48%가 여기서 탈락)
17:50  after_hours_labels           → ah_price·ah_react·ah_volume 적재 (실측 107~163초)
익일 09:03  settle --venue krx_open  절반 매도 + 감시계획
```

## 3. 변경 후 타임라인

```
17:30  closing_bet 회차            → trade_signal 갱신 (이 회차 신호만 사용)
17:50  trading-buy-krx 기동  ← cron 이동
       └ after_hours_labels 완료 대기 (job_run, ~17:53) + 17:30 회차 신호 확인
       └ 시드 배분 → 수량 확정 → 지정가 산정
17:56  전 종목 시간외단일가 지정가 주문 전송 (주문 데드라인)
18:00  마지막 단일가 회차 체결 — 미체결분은 자동 소멸
18:02  fills_sync --venue krx  체결 반영 + 텔레그램 (미체결 0건도 명시)
18:00  gap_check --base-krx 기준가 수집  ← cron 이동
익일 09:03  settle --venue krx_open  (불변)
```

핵심 순서 보장: **17:50 라벨 수집 → 17:56 주문 → 18:00 체결.** 사용자가 지적한 "막판 매수"가
라벨 파이프라인과 정확히 맞물린다. 라벨을 먼저 받아야 2단계 veto 가 성립한다.

---

## 4. 집행 설계 상세

### 4-1. 창 상수 (`trading/workers/signal_executor.py:90` VENUES)

```
"krx": {"exchange": "KRX", "start": (17, 50), "wait_until": (17, 54), "deadline": (17, 56),
        "signal_since": (17, 30), "labels_job": "after_hours_labels"}
```

현행 대기 루프는 `since = 윈도우 시작`으로 신호 신선도를 판정한다(`signal_executor.py:392`).
새 창은 시작(17:50)과 신호 회차(17:30)가 달라지므로 **`signal_since` 를 VENUES 로 분리**한다
(NXT 는 `signal_since == start` 로 두면 동작 불변).

추가로 **`after_hours_labels` 완료 대기**가 필요하다 — `job_run` 에서 당일 `success` 를 확인하는
루프를 넣고, 17:54까지 미완료면 라벨 없이 진행한다(fail-open, 1단계는 라벨을 안 쓰므로 무해).
2단계에서 veto 를 켜면 이 대기가 **필수 선행조건**이 된다.

### 4-2. 주문 유형과 지정가 산정

시간외단일가는 **지정가만 받는다**(시장가·IOC·최유리 전부 불가). `ExecutionEngine._now_trde_tp()`
(`trading/core/execution_engine.py:45`)가 KRX→`3`(시장가)를 돌려주므로 venue 분기가 필요하다.

- **주문가 = min(당일 KRX 종가 × (1 + `AH_BUY_LIMIT_PCT`), 상한가)**, 기본값 `AH_BUY_LIMIT_PCT=2.0%`.
  단일가 경매라 청산가가 지정가보다 낮으면 **청산가로 체결**된다 → 지정가는 체결 가격이 아니라
  **최대 슬리피지 가드**다. 청산가가 지정가를 넘으면 미체결(= 과열 회피).
- **사이징도 지정가 기준**으로 한다(`c["price"]` 에 지정가를 넣는다). 실체결가가 그 이하라
  주문가능금액을 넘길 수 없다. `RiskEngine.check(...)` 의 주문금액도 같은 값을 쓴다.
- 시간외단일가 가격제한은 당일 종가 ±10%(상하한가 이내)라 2% 지정가는 항상 유효 범위다.
- 앵커는 `_krx_close_today()`(`signal_executor.py:266`, ka10081 일봉 당일 캔들)를 그대로 쓴다.
  18시대에 `ka10001 cur_prc` 를 쓰면 KRX 종가인지 시간외가인지 일관되지 않는다(이미 기록된 함정).

### 4-3. 체결 확정이 비동기가 된다 (⚠️ 가장 큰 구조 변화)

현행 KRX 경로는 시장가라 주문 = 체결이었다. 변경 후에는 **18:00까지 체결 여부를 모른다.**

| 항목 | 현행 | 변경 후 |
|---|---|---|
| `trade_signal.status` | 주문 전송 성공 = `done` | 전송 성공은 `executing` 유지 → **18:02 fills_sync 가 `done`/`skipped` 확정** |
| 미체결 주문 | 거의 발생 안 함 | **정상 경로**(과열 미체결·시간외 무거래 9%) |
| `order` 행 | sent → filled | sent → (filled \| 소멸) |

미체결분은 18:00에 거래소에서 소멸한다. `order_maintenance`(익일 개장 중 취소)와
`reconcile`/dead-order 가드가 이를 `canceled` 로 마감하는데, **2026-08-05 사고(전량체결을
canceled 로 오판정)의 4중 가드가 이 경로에 그대로 걸린다** — 미체결 빈도가 올라가므로
착수 시 그 가드(60초 미경과 보류·브로커 체결수량 보존)를 재확인한다.

NXT 의 부분체결 재시도(`_retry_nxt_partial_fill`)는 **KRX 에 적용하지 않는다** — 단일가 경매라
재주문할 회차가 없다.

### 4-4. 그대로 유지되는 것

시드 배분(`seed_allocator`), 확신도 사이징, 레짐·거시·선물 게이트, blocklist, 권리락 스킵,
레버리지 ETF 치환, 멱등키(`{trade_date}:{signal_id}:buy`), 하트비트 — 전부 불변이다.
게이트가 읽는 선물·거시 값이 15:20 대신 17:50 기준이 되는 것만 부수 효과다(야간선물이 더 반영됨).

---

## 5. 파일별 변경 목록

| 파일 | 변경 | 비고 |
|---|---|---|
| `ecosystem.config.js:236` | `trading-buy-krx` cron `0 15` → `50 17` | 주석의 "눌림 추종" 설명도 현행(종가 단일 매수)으로 정정 |
| `ecosystem.config.js:335` | `trading-fills-sync-krx` cron `31 15` → `2 18` | |
| `ecosystem.config.js:85` | `jongalab-gap-base-krx` cron `20 15` → **§5-1 검증 후 확정** | 18:00 정각은 TR 리셋 이후일 수 있다 |
| `trading/workers/signal_executor.py:90` | VENUES krx 시각 + `signal_since` 분리 + 라벨 대기 | |
| `trading/workers/signal_executor.py:619~` | KRX 지정가 산정 분기, 부분체결 재시도 NXT 한정 유지 | |
| ⚠️ `trading/core/execution_engine.py:45` | `_now_trde_tp` 에 시간외단일가 분기 + 지정가 전달 | **민감 파일 — 승인 필수** |
| `trading/core/kiwoom_order_client.py:89` | `trde_tp` 주석에 시간외단일가 코드 추가 | §6 검증 후 확정 |
| `trading/workers/fills_sync.py:31` | krx `hour` 15 → 18, 체결 0건 시 신호 상태 `skipped` 확정 | |
| `trading/api.py:186` | `_monitor_phase` KRX 창 `(15,0)~(15,20)` → `(17,50)~(17,56)` | 모니터 탭 |
| `trading/api.py:316` | `/buy-preview` 윈도우 종료 판정 시각 | GS건설 케이스 로직 |
| `jongalab/workers/gap_check.py:202` | `run_base("krx")` 주석·시각 | `exec_leg_ret` 앵커가 18:00로 바뀜 |
| `trading/README.md`, `jongalab/README.md` | 워커 표·타임라인 갱신 | 같은 턴에 필수 |
| `trading/core/config.py` | `AH_BUY_LIMIT_PCT` 추가(.env 경유) | |

## 5-1. 측정 계층 — 무엇을 바꾸고 무엇을 그대로 두는가 (⚠️ 원장 정합)

성적·지표는 **두 계층**으로 나뉘어 있고, 이 변경은 **집행 계층만** 움직인다.
원장이 이미 경고해 둔 분리다("두 라벨은 진입 기준이 다르다 — 비교 전 반드시 확인",
`docs/history/execution-exit.md`).

| 계층 | 묻는 질문 | 라벨 | 이 변경에서 |
|---|---|---|---|
| **집행** | 우리가 실제로 얼마에 사서 얼마에 팔았나 | `exec_leg_ret`(KRX 분기), `gap_check --base-krx` 기준가 | **바꾼다** (15:20 → 18:00) |
| **선정** | 그날 종가 기준으로 이 종목이 좋았나 | `next_open_ret`·`next_high_ret`·`next_low_ret`·`next_close_ret` (앵커 = 리포트일 **종가**) | **안 바꾼다** |

### 선정 계층을 건드리면 안 되는 이유

`edge_rule_daily` 채점 · `rule_evaluator` · `weight_tuner` · `core/backtest.py` · 승격/강등 게이트가
전부 종가 앵커 위에 쌓여 있다. 앵커를 바꾸면 **rule 전종의 과거 stats 가 무효**가 되고 표본이
리셋된다. 그리고 선정 축이 묻는 것은 "이 종목이 좋았나"이지 "우리가 잘 샀나"가 아니다 —
후자는 `exec_leg_ret` 의 몫이다. 마찬가지로 `krx_close_price`(앵커 컬럼)·`ah_react` 정의
(÷ KRX 종가)·`nxt_gap_pct`·edge_rule 의 `exit_label` 기본값도 전부 유지한다.

`exec_leg_ret` 은 **전환일 이전/이후 표본을 섞어서 분석하지 않는다**(뜻이 다른 값이다 —
지속성 rule v1/v2 때와 같은 처리). `outcome_backfill.py:154` 주석("trading 쪽 시각을 바꾸면 이
라벨도 함께 바꿔야 비교가 유효하다")도 같은 턴에 갱신한다.

### ⚠️ 미해결 — 18:00 체결가를 잡을 수단이 확정되지 않았다

집행 계층 라벨을 옮기려면 **18:00 시간외단일가 체결가**가 필요한데, 현재 수단이 셋 다 흠이 있다.

| 후보 | 문제 |
|---|---|
| `ka10087`(시간외 TR) | 16~18시에만 값이 살아있고 **종료 후 0 리셋** → 18:00 정각 수집은 이미 늦다. 17:59 수집은 18:00 회차가 아니라 **17:50 회차 체결가**다 |
| 분봉(`build_minute_price_by_time`) | `exec_leg_ret` 이 쓰는 경로. **KRX 분봉에 시간외단일가 체결이 찍히는지 미확인** — 안 찍히면 18:00 leg 가 영구 NULL |
| 실체결가(trading `fill`) | 매수 종목엔 정확하지만 **유니버스 전체엔 없다**(`exec_leg_ret` 은 비선정 포함 유니버스 라벨). 도메인 경계(trading → jongalab)도 넘는다 |

→ §6 에 검증 항목으로 걸었다. **분봉에 시간외 체결이 포함되면 가장 깔끔하다**(코드 변경이
`"1520"` → `"1800"` 문자열 하나로 끝나고 유니버스 전체가 커버된다). 포함되지 않으면
차선은 "매수 종목만 `fill` 실체결가로 집행 성적을 별도 집계"이고, 그 경우 `exec_leg_ret` KRX
분기는 **비우고**(폴백 고착 방지) 집행 성적은 trading 대시보드 실현손익으로만 본다.

이 검증 결과가 나오기 전에는 §5 의 `gap-base-krx` cron 이동도 확정하지 않는다.

---

## 6. 선행 검증 (착수 전, 자금 투입 없이)

1. **키움 REST `kt10000` 의 시간외단일가 주문구분 코드 확인.** 현재 클라이언트 주석
   (`kiwoom_order_client.py:89`)에 `0/3/5/6/7/10/20` 만 있고 시간외 코드가 없다. 구 OpenAPI 계열의
   `61`(장전시간외종가)·`62`(시간외단일가)·`81`(장후시간외종가) 대응 여부가 **미확인**이다.
   → `trading/test_live_buy.py` 로 저가 종목 **1주** 지정가 주문을 16:00~18:00 세션에 넣어
   수락/거부와 `return_msg` 를 확인한다. 거부되면 이 설계는 **성립하지 않는다**(중단 지점).
2. **`dmst_stex_tp`**: `KRX` 로 충분한지(시간외 전용 값 요구 여부) 같은 테스트에서 확인.
3. **미체결 소멸 동작**: 체결 불가 지정가(예: 하한 근처 매수)로 1주 주문 → 18:00 이후
   `ka10075` 미체결 조회와 `order` 행 상태 전이를 관찰한다(§4-3 가드 확인).
4. **ETF 취급**: 레버리지 치환이 켜져 있으면 대상이 ETF 가 된다 → ETF 의 시간외단일가 주문
   수락 여부를 1주로 별도 확인한다.
5. **분봉에 시간외단일가 체결이 포함되는가** (§5-1 미해결 항목). 자금 투입 없이 조회만으로
   판정된다 — 시간외 거래가 있었던 KRX 전용 종목 하나로
   `build_minute_price_by_time(api, code, nxt=False, base_dt=<과거일>)` 을 돌려 **16:00~18:00 구간
   봉이 존재하는지** 확인한다(`max_pages` 를 늘려야 그 시간대까지 닿을 수 있다).
   대조군으로 같은 날 `ah_price`(17:50 스냅샷)와 값을 맞춰본다.
   - 포함 → `exec_leg_ret` KRX 분기를 `"1520"` → `"1800"` 으로 바꾸면 끝. `gap_check --base-krx` 는
     분봉 소급이 가능하므로 cron 을 아예 없애도 된다.
   - 미포함 → §5-1 차선(실체결가 별도 집계)으로 가고, `exec_leg_ret` KRX 분기는 비운다.
6. **`ka10087` 리셋 시각 실측**: 18:00:00 / 18:01 / 18:05 에 같은 종목을 조회해 값이 언제 0이
   되는지 본다. 5번이 미포함으로 판정됐을 때만 필요하다(17:59 스냅샷의 유효성 판단용).

---

## 7. 리스크와 대응

| 리스크 | 크기 | 대응 |
|---|---|---|
| 주문구분 코드 미지원 | **치명(설계 무효)** | §6-1 선행 검증. 거부 시 착수하지 않는다 |
| 미체결로 그날 매수 누락 | 중 (실측 9%가 시간외 무거래) | 기회비용일 뿐 손실이 아니다. fills_sync 알림에 미체결 종목 명시 |
| 과열 종목 미체결(지정가 캡) | 낮음 | 의도된 동작. `AH_BUY_LIMIT_PCT` 로 조절, **밴드 튜닝 반복 금지** |
| 18시대 무인 시간대 실패 | 중 | 매수 워커는 `watchdog` 감시 대상이 아니다(매도 전용). fills_sync(18:02)가 "체결 0건"을 보고하도록 해 침묵 실패를 없앤다 |
| 보유 시간 2.6h 단축 | 낮음 | 엣지는 오버나잇 갭이라는 게 기존 판정. 오히려 노출 축소 |
| 반차 거래일(폐장일 등) 시간 변동 | 낮음 | 시간외단일가 시각이 단축되는 날이 있다. `market_calendar` 에 예외가 없으므로 그런 날은 미체결로 스킵된다(안전한 실패) |
| 라벨 워커 지연 → veto 미적용 | 2단계에서만 | 17:54 미완료 시 fail-open. 다만 2단계에서는 **veto 없이 매수**가 되므로 audit 에 명시 기록 |
| 다중검정 | 중 | 이 축에서 이미 여러 분석을 돌렸다. 1단계는 사후 채점으로만 판정하고, 2단계는 승격 게이트를 그대로 통과시킨다 |
| **집행 성적을 못 재게 됨** | 중 | §5-1 미해결 항목. 18:00 체결가 수단이 없으면 `exec_leg_ret` KRX 분기가 비고, 전환 효과를 사후 채점할 수 없다 → §6-5 를 **착수 전에** 판정한다 |

---

## 8. 단계

### 1단계 — 매수 시점만 이동 (veto 없음)

§5 변경 전부 + §6 선행 검증. 이것만으로 선정 신선도(48% 탈락 해소) · 15:30~18:00 공시/뉴스 veto ·
진입가 할인을 동시에 얻는다. **veto 표본을 기다릴 이유가 없는 부분이다.**

### 2단계 — `veto_ah_react_down` 집행 레이어 승격 (표본 15건+ 충족 후)

`trading/core/edge_execution.py` 가 NXT 갭에 쓰는 "원장 predicate 를 주문 직전에 평가" 구조를
그대로 재사용한다. `EXEC_FILLED_COLS` 에 `ah_react`·`ah_volume` 을 더하면
`is_execution_layer_rule()` 이 이 rule 을 집행 레이어로 인식한다. 하드코딩이 아니라 원장 rule 이라
채점·강등 감시가 자동으로 붙는다(2026-08-03 하드코딩 후 되돌린 이력 참조).

제약 2개는 그대로 상속된다 — ① 종목 추가 불가(거른 몫의 시드는 논다) ② 그 rule 이 혼자
데려온 종목만 대상(`in_scope`). 승격 판정 시 **대체효과 재계산 + 일 클러스터 t** 는
`edge-gate-discipline` 규율대로 다시 계산한다(현재 t=3.52 는 n=5 값이다).

### 부수 — closing_bet 회차별 순위 스냅샷 적재

§1-① 의 lookahead 를 없애고 1단계의 사후 채점 근거가 된다. `daily_stock_report` upsert 는 그대로
두고, 회차마다 `(report_date, run_at, stock_code, rank_no, selected)` 만 별도 테이블에 append 한다.
1단계와 **독립**이므로 먼저 넣어도 된다(오히려 먼저 넣으면 전환 전 baseline 이 쌓인다).

---

## 9. 검증 · 롤백

**검증**(테스트 없는 프로젝트 표준):
1. `uv run --directory trading --group dev pytest` — 자금 경로 단위 테스트. 동작이 바뀌므로
   `tests/test_edge_execution.py`·execution_engine 계약 테스트를 함께 갱신한다.
2. `uv run --directory trading python -m py_compile <변경 파일>`
3. `uv run --directory jongalab python -m py_compile workers/gap_check.py`
4. 트레이딩 프론트 `npx tsc --noEmit && npm run lint` (창 표기 변경 시)
5. 첫 실거래일 18:02 audit 확인: `buy_start`(창 17:50~17:56) · `buy_exec`(지정가) ·
   `buy_response` · fills_sync 체결/미체결 분류가 의도대로인지 **전건 육안 확인**.

**롤백**: `ecosystem.config.js` cron 3개 + `VENUES["krx"]` 시각만 되돌리면 원복된다. 지정가 분기는
**venue 로 격리**해 두므로(공용 경로를 바꾸지 않는다) 남아 있어도 KRX 15:20 시장가 동작에 영향이
없다. 롤백 판단 트리거는 "미체결률 > 30% 2일 연속" 또는 "주문 거부 발생".

## 10. 근거 수치 재현

```sql
-- ① 선정 신선도 (trading DB 에서 jongalab 크로스 조인)
SELECT a.stk_cd, DATE(a.created_at) d, r.selected, r.rank_no, r.next_open_ret
FROM audit_log a JOIN jongalab.daily_stock_report r
  ON r.stock_code = a.stk_cd AND r.report_date = DATE(a.created_at)
WHERE a.event = 'buy_exec' AND HOUR(a.created_at) = 15
  AND a.created_at >= NOW() - INTERVAL 90 DAY;   -- payload.sent = true 만 집계

-- ②③ 시간외 반응 · 진입가 (jongalab DB)
SELECT report_date, stock_code, krx_close_price, ah_price, ah_react, ah_volume,
       gap_krx_price, next_open_ret, selected
FROM daily_stock_report
WHERE nxt_listed = 0 AND ah_price > 0 AND report_date >= CURDATE() - INTERVAL 120 DAY;
```

집계 규약: veto 판정은 **대체효과**(제외군 평균 − 잔여군 평균)로 재고, 진입가 비교는
`exec_leg_ret` 이 아니라 위 가격 컬럼으로 직접 계산한다(라벨 정의가 venue 마다 다르다).

---

## 11. 착수 시 기록할 곳

- 구현 전 판정·수치 → `docs/history/edge-ledger.md` 에 "2026-07-31 매수경로 부재 판정의 전제 변경"
  항목으로 추가(이 문서 §1 요약 + 재현 쿼리).
- 집행 시각·주문 유형 변경 자체 → `docs/history/execution-exit.md` (`exec_leg_ret` KRX 분기 정의
  변경 포함, 표본 분리 경고와 함께).
- 구조·현재 파라미터 → `trading/README.md`·`jongalab/README.md` (같은 턴에 갱신).
