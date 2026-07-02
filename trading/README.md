# trading — 자동매매 집행 서버

jongalab 이 만든 매수 신호(`trade_signal`)를 받아 **실제 주문을 집행하고 포지션·리스크를 관리**하는
전용 서버 (FastAPI `:8002`) + 독립 대시보드(`frontend/`, `:3001`).
이 도메인만 **주문 권한**을 가진다.

- 시세·수급은 kiwoom 데이터 서버(`:8001`)에서 **읽기**, 주문/계좌는 kiwoom REST 를 **직접 호출**한다
  (`core/kiwoom_order_client.py`). kiwoom 데이터 서버의 읽기 전용 불변식은 그대로 유지된다.
- 토큰은 `kiwoom` DB 의 공유 토큰을 **읽기 전용**으로 쓴다(발급/갱신은 kiwoom 워커 담당).

> ⚠️ `core/risk_engine.py`·`core/execution_engine.py` 는 **자금 손실에 직결되는 민감 로직**이다
> (가드 훅이 편집 차단). 수정 전 반드시 사용자 확인을 받고 변경 내용을 명시한다.
>
> 이 README 는 주요 로직·코드 구조의 소스 오브 트루스다. 집행/리스크/청산 로직을 바꾸면
> **이 파일도 함께 갱신**한다. 작업 규칙은 루트 [`AGENTS.md`](../AGENTS.md) 를 따른다.

---

## 경계
- `jongalab`(closing_bet) 가 **무엇을 살지** 결정 → `trade_signal` 적재
- `trading` 이 **언제·얼마나·어떻게 집행**하고 포지션/리스크를 관리 (단방향, 신호만 읽음)

---

## 코드 구조

```
trading/
├── api.py                      # FastAPI(:8002) — 대시보드 백엔드 + 헬스/킬스위치/리스크설정
├── core/
│   ├── config.py               # .env, TRADING_MODE, 킬스위치, 한도/튜닝 파라미터
│   ├── db.py                   # get_db(trading) / get_kiwoom_db / get_jongalab_db
│   ├── risk_engine.py          # ⚠️ 게이트키핑: 킬스위치·일일한도·서킷브레이커
│   ├── execution_engine.py     # ⚠️ 주문 사이징·집행·멱등키
│   ├── seed_allocator.py       # 시드 배분(거래소별): 상위10 선정(점수순)·등가중 배분·최소투입 우선 그리디·종목당 시드50% 캡
│   ├── regime_gate.py          # 롤링 엣지 게이트: 최근 선정종목 점수판별력(익일시가 상위½−하위½)이 역전이면 총 시드 축소
│   ├── futures_gate.py         # 선물 환경 게이트(NXT 전용): 매수시점 NQ·야간선물 하락 시 섹터별 차등 감액(반도체·IT 더, 방어주 덜)
│   ├── kiwoom_order_client.py  # 키움 REST 직접 호출(kt10000~3 주문, kt00018 잔고, ka10074~6)
│   ├── kiwoom_data_client.py   # kiwoom 데이터 서버(:8001) 읽기(현재가·NXT·차트)
│   ├── fill_sync.py            # 실거래 체결 동기화(ka10076 → fill/position)
│   ├── order_maintenance.py    # 스테일 주문 취소·미체결(dead) 정리
│   ├── position_manager.py     # 포지션 조회·평가손익(청산 후보는 미구현)
│   ├── notifications.py        # 텔레그램 관리자 알림
│   └── repository/             # DB 접근 계층
│       ├── trade_signal.py     # jongalab 신호 수신(pending→done)
│       ├── order.py            # 주문 의도/전송 추적 + 멱등키
│       ├── fill.py             # 체결 기록(수량·가격·수수료·세금)
│       ├── position.py         # 보유 포지션(평단·실현손익)
│       ├── settle_plan.py      # 청산 계획(stop_price, 트레일링)
│       ├── risk_state.py       # 일자별 상태(주문수·실현손익·브레이커)
│       ├── risk_config.py      # 리스크 한도(JSON, 대시보드 편집)
│       ├── blocklist.py        # 자동매매 제외 종목(수동 보유분)
│       ├── audit_log.py        # 불변 append-only 이벤트 로그
│       └── kiwoom_token.py     # 공유 토큰 읽기 전용
├── workers/                    # PM2 cron (스케줄은 루트 ecosystem.config.js)
├── frontend/                   # Next.js 대시보드(:3001)
├── sql/                        # trading DB 스키마
└── tests/                      # 자금 경로 단위 테스트 (pytest, DB/네트워크 없이 fake 주입)
```

---

## 집행 흐름 (신호 → 체결 → 청산 → 정합성)

종가베팅 1사이클을 거래소(KRX/NXT)별로 집행한다.

```
[jongalab closing_bet] → trade_signal(pending)
        │
signal_executor (KRX 15:00 / NXT 19:30)
  · 블록리스트 제외 → 거래소 분류 → 시드 산정 → **regime_gate(역전 레짐)로 총 시드 축소** → seed_allocator 등가중 배분 → **futures_gate(선물 하락, NXT만) 섹터별 수량 감액**
  · 15초 폴링으로 장중 고점 추적, 고점 대비 되돌림(BUY_PULLBACK_PCT) 시 매수(IOC)
  · 마감 시각에 잔여분 시장가 집행 → 신호 status 갱신(done/skipped/rejected)
  · 주문 직전 live 주문가능금액(100stk_ord_alow_amt) 재조회로 수량 보정 — 시드는 윈도우 시작
    1회 스냅샷이라, 앞선 종목 체결·증거금 선반영으로 줄어든 현금에 마지막 종목이 '증거금
    부족'으로 통째 거부되지 않도록 살 수 있는 최대 수량으로 축소(0이면 스킵)한다(execution_engine).
        │
fills_sync (15:31 / 19:55) · ka10076 체결 동기화 → position 갱신 + 매수 텔레그램 알림
        │
settle --venue nxt (08:03)      · NXT 상장 종목: NXT 시초가로 갭 판정 → 절반 매도(tag=nxt) → settle_plan 생성
settle --venue krx_open (09:03) · NXT 미상장 종목: KRX 개장가로 갭 판정 → 절반 매도(tag=krxopen) → settle_plan 생성
  · 두 단계는 동일 전략(_run_open_stage 공용). 대상 종목 집합·거래소(NXT 최유리IOC / KRX 시장가)·tag 만 다르다.
  · NXT 미상장 종목은 NXT 호가가 없어 08:03 를 건너뛰고, KRX 정규장 개장(워밍업 후) 09:03 에 처리한다.
  · 집행 시각 :03 근거(실측): NXT 는 프리마켓 갭상승이 첫 5분간 식어 08:03 이 08:05 대비 평균 +0.35%
    (08:00~08:01 은 얇은 단발 호가 허수가 끼어 제외). KRX 불가 종목은 개장 드리프트가 없어(평균 ≈0%)
    시점 중립이라 :03 으로 통일. KRX 상장 종목과 달리 NXT 불가 종목엔 "1분이 더 높다"가 성립하지 않는다.
monitor (08:01~09:30, 15초 폴링)
  · 하드 손절(HARD_STOP_LOSS_PCT) · 트레일링 스톱(TRAIL_PCT, 단조 상승) → 돌파 시 전량 매도(tag=stop)
  · 스테일 주문 취소 + dead 주문 정리 + 체결 동기화(유지보수 단계는 각자 격리 — 실패해도 손절/스탑 감시는 계속) + 하트비트 로그(대시보드 표시; check_once 성공 시에만 찍어 점검 실패가 '신호 없음'으로 드러남)
settle --venue krx (09:28) · 잔여 보유분 전량 청산(마감 데드라인) → 오버나잇 방지
        │
reconcile (20:00) · kt00018 잔고 vs 로컬 position 대조 → 드리프트 알림
```

> **첫 구현 범위는 종가베팅 집행만**이다. 장중 상시 손절 감시(`position_monitor`)·멀티 전략은 다음 단계.

**미실행 감시(dead-man's switch)**: monitor·settle 은 cron 미발동·크래시로 안 돌아도 스스로 알리지
않으므로(거래 없으면 조용히 끝남), 각 워커가 성공 완료 시 `audit_log` 에 `worker_done` 마커를 남긴다.
`watchdog.py`(평일 09:35)가 핵심 워커(`settle:nxt`/`settle:krx_open`/`settle:krx`/`monitor`)의 마커 누락을 확인해 경보한다.
마커 유무만 보므로 무거래일에도 오경보가 없다. 감시 대상 추가는 `watchdog.CRITICAL_WORKERS` 에 한 줄.

---

## 안전장치 (구현됨)
| 장치 | 위치 | 내용 |
|---|---|---|
| 모드 | `config.py`, `execution_engine.py` | `TRADING_MODE=paper`(기본, 미전송·즉시 시뮬레이션) / `live`(실주문) |
| 글로벌 킬스위치 | env `TRADING_KILL_SWITCH=1` + DB `kill_switch` | 둘을 OR — 하나라도 켜지면 전체 차단 |
| 서킷브레이커 | `risk_engine.py` + `risk_state.py` | 일일 실현손실 ≤ -MAX_DAILY_LOSS 시 자동 킬스위치 발동 |
| 하드 한도 | `risk_engine.py` | 일일 주문수(기본 20, **매수만 카운트** — 청산 매도는 제외). 종목당 명목금액·동시 보유종목수 상한은 제거됨(상위 종목 집중 배분을 위해 — `MAX_NOTIONAL_PER_NAME`/`MAX_POSITIONS` 는 `execution_engine` 폴백 사이징 용도로만 존치) |
| 멱등키 | `execution_engine.py`, `order.py` | `YYYYMMDD:signal_id:side` UNIQUE — cron 재실행 중복 방지(거부 `:x<id>`, dead `:dead:<id>` 접미사로 키 해제 — id 로 고유성 보장) |
| 하드 손절 / 트레일링 | `monitor.py`, `settle_plan.py` | HARD_STOP_LOSS_PCT 즉시 전량 / TRAIL_PCT 단조 상승 스톱 |
| 불변 감사로그 | `audit_log.py` | append-only(UPDATE/DELETE 없음) |
| 블록리스트 | `blocklist.py`, `signal_executor.py` | 수동 보유 종목 자동매수 차단 |
| 롤링 엣지 게이트 | `regime_gate.py`, `signal_executor.py` | 최근 REGIME_WINDOW_DAYS 선정종목의 점수 판별력(익일시가 상위½−하위½ 스프레드)이 역전이면 총 시드를 REGIME_MIN_MULT(기본 0.3)까지 선형 축소. jongalab `daily_stock_report.next_open_ret` 읽기전용 조회, 표본<REGIME_MIN_SAMPLES 면 미개입(1.0). 축소 시 `audit_log('regime_gate')` → 모니터 탭 활동 피드에 사유 노출. `/buy-preview`(매수 예정)도 동일 배수로 시드를 미리 반영·표시 |
| 선물 환경 게이트(섹터 차등) | `futures_gate.py`, `signal_executor.py` | **NXT(19:50) 전용.** 매수시점 NQ 선물(jongalab market-indices)+코스피200 야간선물(jongalab DB `kis_night_future`, 신선도 FUTURES_STALE_SEC 초과 시 미개입) 방향으로, seed_allocator 등가중 배분 뒤 **종목 섹터(키움 업종명, `ticker_dictionary`)별 keep-factor(≤1.0)로 수량 감액**. 섹터 클래스별 축 민감도: 반도체·IT(NQ 민감)·경기민감주(자동차·화학·금융, 지수 민감)를 더 깎고 통신·음식료 등 방어주를 덜 깎음. `keep=∏_axis(1−MAX_CUT×민감도)`(하락 축에만), 하한 FUTURES_SECTOR_MIN_KEEP(0.25). 상승이면 감액 없음(reduce-only). **결합 하한**: 레짐×선물 곱이 SEED_COMBINED_MIN_MULT(0.3) 밑으로 안 내려가게 종목 keep 을 `effective_keep()` 로 클램프(REGIME_MIN_MULT>=이 값이어야 보장, 기본 둘 다 0.3). 지표 취득 실패면 미개입. 매 적용을 audit_log(`futures_gate`)에 선물값+섹터별 keep 스냅샷으로 기록 → 모니터 탭 활동 피드에 사유(NQ·야간선물 등락, 감액 종목수·섹터) 노출. `/buy-preview`도 동일 로직으로 예상 수량을 미리 감액·표시(야간세션 개장 전이면 미개입·"대기" 표기). ⚠️ **섹터 민감도는 통설 기반 미검증 가정** — 추후 stk_cd→섹터 조인으로 실측 후 재튜닝 |
| 정합성 점검 | `reconcile.py` | 매일 브로커 잔고 vs 로컬 포지션 대조 |
| 미실행 감시(dead-man's switch) | `watchdog.py` + `audit_log` worker_done 마커 | 핵심 워커가 완료 시 마커를 남기고, watchdog(평일 09:35)가 마커 누락 시 텔레그램 경보 |

튜닝 파라미터(`config.py`): `BUY_PULLBACK_PCT`(되돌림 매수), `STOP_BUFFER_PCT`(갭다운 버퍼),
`TRAIL_PCT`(트레일링), `HARD_STOP_LOSS_PCT`(하드 손절).

---

## 프론트엔드 (`frontend/`, :3001)
홈(당일 손익·매수·보유·매수 프리뷰) · 모니터(워커 하트비트·활성 플랜) · 히스토리(월/일 주문) ·
캘린더(월간 손익) · 설정(킬스위치·리스크 한도·블록리스트). 관리자 비밀번호 로그인(httpOnly 쿠키).

**미체결 사유**: 히스토리 탭은 `GET /orders` 응답의 `reason` 으로 체결 안 된 항목의 이유를 표시한다.
- 거부(rejected)는 키움 거부 메시지(`audit_log.reject_reasons_by_order_ids` — buy/sell_rejected payload 의
  order_id↔resp.return_msg 매칭, 코드 래퍼 제거), 그 외(canceled/sent/intended)는 상태 기반 일반 사유.
- 주문 행이 안 생기는 **매수 스킵/차단**(배분 0주·블록리스트·리스크 차단·주문가능액 부족)도 `month` 조회 시
  `audit_log.buy_skips_by_month`(buy_skip/buy_blocked/buy_skipped)로 order 와 같은 모양(`status='skipped'`,
  `kind='skip'`)으로 만들어 주문과 한 목록에 시간순으로 섞는다. 프론트는 스킵 행은 수량/가격 없이 사유만 보여준다.

**청산 종목 워커 로그**: 홈·캘린더의 청산 목록(`RoundTrips`)에서 종목을 누르면 모달로
① **1분봉 차트**(매수날 15:00~매도날 10:00 + 매수/매도 타점)와 ② **워커 활동 트레일**
(매수 집행 → 갭/스탑 모니터 → 매도 체결)을 함께 보여준다.
- 차트: `GET /stock-chart` (`KiwoomDataClient.get_minute_chart_pages` ka10080 → 구간 필터·시간순).
  **NXT+KRX 합본** — 정규장(09:00~15:30)은 KRX 봉, 그 밖(NXT 프리/애프터마켓: 오후 매수·시초가
  청산)은 NXT(`{stk_cd}_NX`) 봉으로 한 시계열을 만든다(분 단위 중복은 KRX 우선). lightweight-charts
  는 거래 없는 야간 구간을 자동으로 접어 연속 표시한다. 프론트는 `lightweight-charts`(한국식 색)로
  렌더링하고, 타점은 체결 이벤트(시각·가격)를 가장 가까운 캔들로 스냅해 표시한다(`MinuteChart`).
- 로그: `GET /stock-events` (`audit_log.list_by_stock`, 하트비트·주문응답 원문 제외).
  이벤트 라벨/설명 렌더링은 모니터 탭과 `lib/events.ts` 를 공유한다.
- 구간(차트·로그 공통): 매수날≠매도날이면 **매수날 15:00~매도날 10:00**(`_trade_window`).
  종가베팅은 오후(15:00 KRX/19:30 NXT) 매수·오전(08:03 NXT/09:03 KRX) 청산이라 이 구간이 한
  사이클(매수→청산)을 딱 감싸, 같은 종목을 여러 날 매매해도 인접 사이클이 섞이지 않는다(같은 날이면 그 날 전체).
  단, **1회 매수를 여러 날 나눠 판 분할/이월 청산**이면(매수일 15시~매도일 사이에 이미 매도가 있었음,
  `_effective_start`+`audit_log.has_sell_between`) 뒤 매도일은 다음 사이클이라 **매도 당일만** 본다
  — 원매수일까지 거슬러 올라가 이전 청산이 섞이지 않게 한다(주말 끼고 다음날 청산하는 정상 사이클은 영향 없음).
- 매수처 짝짓기(`_build_roundtrips`)는 order 매수 + **수동 매수**(`audit_log.latest_manual_buys_before`)를
  합쳐 매도일 직전 최신 매수를 고른다. NXT 일일 한도 초과로 자동 매수가 막힌 분을 사람이 수동 체결·연동한
  `manual_buy_link` 는 order 테이블에 없어, 이게 없으면 그 매도가 엉뚱한 옛 매수에 묶여 매수가·구간이 틀어진다.
  수동 매수의 매수 시각은 그 분을 메우는 직전 자동매수 시도(buy_exec/buy_blocked) 시각으로 본다(연동은 새벽 일괄).

## 기동
```bash
uv run --directory trading uvicorn api:app --host 127.0.0.1 --port 8002   # API
cd trading/frontend && npm run dev                                        # 대시보드(:3001)
```

## 테스트 (자금 경로)
`tests/` 는 자금 손실에 직결되는 순수 로직의 동작을 **DB·키움 네트워크 없이** 고정한다
(fake 협력 객체 주입 + repository 함수 monkeypatch). 커버리지: 시드 배분(`seed_allocator`),
멱등키·사이징·paper 체결 시뮬레이션(`execution_engine`), 한도·서킷브레이커 분기(`risk_engine`),
롤링 엣지 게이트 배수 매핑·역전 판정(`regime_gate`), 선물 섹터 게이트 클래스 매핑·섹터별 keep 차등·미개입 분기(`futures_gate`).
민감 파일(`risk_engine.py`·`execution_engine.py`)은 **수정하지 않고 동작만 핀**한다.
```bash
uv run --directory trading --group dev pytest
```
집행/리스크 로직을 바꾸기 전·후로 이 테스트를 돌려 회귀를 막는다(바뀐 동작은 테스트도 함께 갱신).

## 유지보수
1. 5가지 사전 검토(필요성·기존 코드·최단 구조·최소 혼란 흐름·유지보수성) 후 착수.
2. 변경 전 이 README 로 흐름·안전장치를 파악하고, 변경 후 해당 섹션을 갱신한다.
3. `risk_engine.py`·`execution_engine.py` 는 사용자 확인 없이 수정 금지.
4. 검증: `uv run --directory trading python -m py_compile <file>`, `paper` 모드로 동작 확인 후 보고.
