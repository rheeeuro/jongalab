# trading — 자동매매 집행 서버

jongalab 이 만든 매수 신호(`trade_signal`)를 받아 **실제 주문을 집행하고 포지션·리스크를 관리**하는
전용 서버(FastAPI `:8002`) + 독립 대시보드(`frontend/`, `:3001`). 이 도메인만 **주문 권한**을 가진다.

- 시세·수급은 kiwoom 데이터 서버(`:8001`)에서 **읽기**, 주문/계좌는 kiwoom REST 를 **직접 호출**한다
  (`core/kiwoom_order_client.py`). kiwoom 데이터 서버의 읽기 전용 불변식은 그대로 유지된다.
- 토큰은 `kiwoom` DB 의 공유 토큰을 **읽기 전용**으로 쓴다(발급/갱신은 kiwoom 워커 담당).

> ⚠️ `core/risk_engine.py`·`core/execution_engine.py` 는 **자금 손실에 직결되는 민감 로직**이다
> (가드 훅이 편집 차단). 수정 전 반드시 사용자 확인을 받고 변경 내용을 명시한다.
>
> 이 README 는 **현재 구조와 상태**의 소스 오브 트루스다. 집행/리스크/청산 로직을 바꾸면 이 파일도
> 함께 갱신한다. **판정 이력·백테스트 수치·사고 경위는 여기 쓰지 않는다** —
> [`docs/history/`](../docs/history/)(특히 `execution-exit.md`·`gates-sizing.md`)에 남긴다.
> 작업 규칙은 루트 [`AGENTS.md`](../AGENTS.md) 를 따른다.

---

## 경계
- `jongalab`(closing_bet) 가 **무엇을 살지** 결정 → `trade_signal` 적재
- `trading` 이 **언제·얼마나·어떻게 집행**하고 포지션/리스크를 관리 (단방향, 신호만 읽음)

### `trade_signal` 계약
jongalab→trading 유일한 결합점. trading 은 `trade_date·stk_cd·stk_nm·rank_no·score·status` 를 읽어
집행한다. `rule_names`(nullable) 는 선정 근거 edge_rule name 콤마 목록으로 jongalab 이 채우며
**시드 배분의 확신도 계산에만** 쓰인다(NULL = legacy 점수 선정 → 전원 1표 = 등가중).
실현손익→가설 귀속은 jongalab 이 `trade_signal ⨝ audit_log/fill` 로 계산한다.
`rules` 모드 무거래일엔 신호 자체가 없다.

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
│   ├── seed_allocator.py       # 시드 배분(거래소별): 확신도(선정 근거 표) 비례 · 표 대비 최소투입 우선 그리디 · 종목당 캡
│   ├── regime_gate.py          # 롤링 엣지 게이트(점수 판별력 역전 시 총 시드 축소) — 기본 OFF, 관찰 로그만
│   ├── futures_gate.py         # 선물 환경 게이트(KRX·NXT): NQ+코스피선물 하락 시 섹터별 차등 감액
│   ├── macro_gate.py           # 거시 이벤트 게이트: 보유 창 sev3 이벤트 시 시드 keep 축소 + 프록시 관찰
│   ├── ex_rights.py            # 권리락 스킵 조회(jongalab ex_rights_schedule 읽기 전용)
│   ├── news_veto.py            # 뉴스 베토 조회(jongalab news_veto_verdict 읽기 전용, 60s TTL)
│   ├── edge_execution.py       # 집행 레이어 rule 판정(원장 live rule × 19:50 실시간 갭)
│   ├── edge_predicate.py       # predicate 평가기(jongalab 원본의 복제 — 드리프트 테스트로 고정)
│   ├── market_calendar.py      # 거래일 판별(jongalab 복제): XKRX + EXTRA_HOLIDAYS
│   ├── kiwoom_order_client.py  # 키움 REST 직접 호출(kt10000~3 주문, kt00018 잔고, ka10074~6)
│   ├── kiwoom_data_client.py   # kiwoom 데이터 서버(:8001) 읽기 + 실시간 피드 캐시 우선(attach_feed)
│   ├── price_stream.py         # 모니터 탭 실시간 시세 공급자(표시 전용, 주문·판정 미경유)
│   ├── realtime_feed.py        # 키움 WS 구독(0B 체결 · 00 주문체결통보 · 0w 프로그램매매) — 항상 옵셔널
│   ├── fill_sync.py            # 실거래 체결 동기화(ka10076 → fill/position)
│   ├── order_maintenance.py    # 스테일 주문 취소·미체결(dead) 정리
│   ├── position_manager.py     # 포지션 조회·평가손익
│   ├── notifications.py        # 텔레그램 관리자 알림
│   ├── logging_setup.py        # 로그 설정
│   └── repository/             # trade_signal · order · fill · position · settle_plan · risk_state
│                               # · risk_config · blocklist · leverage_map · audit_log · kiwoom_token
├── workers/                    # PM2 cron. 전 워커가 진입부에서 휴장일 차단(core/market_calendar)
├── frontend/                   # Next.js 대시보드(:3001)
├── sql/                        # trading DB 스키마
└── tests/                      # 자금 경로 단위 테스트 (pytest, DB/네트워크 없이 fake 주입)
```

---

## 집행 흐름 (신호 → 체결 → 청산 → 정합성)

종가베팅 1사이클을 거래소(KRX/NXT)별로 집행한다.

```
[jongalab closing_bet] → trade_signal(pending)
        │   ※ closing_bet 이 30분마다 재실행되며 후보에서 빠진 잔여 pending 을 expired 로 정리하므로
        │     jongalab 쪽 veto 는 자금 경로 코드 없이 19:30 NXT 매수를 취소한다.
        │     KRX 15:20 기체결분은 되돌릴 수 없어 익일 news_guard 담당.
        │
signal_executor (KRX 15:00 / NXT 19:30 창 시작)
  · 블록리스트 제외 → 권리락 제외 → (레버리지 토글 on 이면 ETF 치환) → 거래소 분류 → 시드 산정
    → 최초 시드 배율(risk_config SEED_INIT_MULT, 게이트보다 먼저) → regime_gate(기본 OFF)
    → 확신도 산정 → seed_allocator 표 비례 배분 → futures_gate × macro_gate(수량·시드 감액)
    → 데드라인 종가 매수. NXT 는 그 직전에 집행 레이어 rule(NXT_GAP_FILTER_ENABLED)이 한 번 더 가른다
  · **종가 단일 매수** — 윈도우 시작에 수량을 확정하고 데드라인(15:20 KRX 동시호가 / 19:50 NXT 최유리IOC)에
    전 종목 매수한다. 윈도우 동안은 하트비트만(대시보드 가동 표시)
  · **시드 배율만 데드라인 직전 재조회** — 윈도우 중간에 대시보드에서 `SEED_INIT_MULT` 를 낮췄으면
    확정 수량을 그 비율만큼 축소한다(축소 전용). 사람이 장중에 노출을 줄이는 유일한 수동 레버라 예외로 둔다
  · NXT 부분체결은 ka10076 으로 확인해 잔량을 최대 2회 별도 멱등키(`:partial:N`)로 재시도.
    체결내역이 아직 안 보이면 과매수 방지를 위해 재시도하지 않는다
  · 데드라인 집행 직전 **체결통보(WS `00`)만 구독**해 고정 대기 대신 통보를 기다린다(구독 실패·미수신 시
    종전 고정 대기와 동일 동작)
  · 주문 직전 live 주문가능금액을 재조회해 수량을 보정한다(앞선 종목 체결로 줄어든 현금에 마지막 종목이
    통째 거부되지 않도록. 0이면 스킵)
        │
fills_sync (15:31 / 19:55) · ka10076 체결 동기화 → position 갱신 + 매수 텔레그램 알림
        │
settle --venue nxt (08:03)      · NXT 상장 종목: NXT 시초가로 갭 판정 (tag=nxt)
settle --venue krx_open (09:03) · NXT 미상장 종목: KRX 개장가로 갭 판정 (tag=krxopen)
  · **갭 방향 무관 절반 매도 + 잔량 plan 생성. 갈리는 건 초기 스탑선뿐이다** —
    갭상승 = **시초가(:03) 한 틱 아래**(버퍼 없음, 한 틱만 밀려도 모니터가 잔량 청산) /
    갭하락 = 저가이탈선(시초가−STOP_BUFFER_PCT 버퍼, 회복 대기)
    (1주는 절반=0 이라 매도 없이 전량 보유로 감시)
  · 두 단계는 동일 전략(`_run_open_stage` 공용). 대상 종목 집합·거래소·tag 만 다르다
  · NXT 미상장 종목은 NXT 호가가 없어 08:03 을 건너뛰고 KRX 개장(워밍업 후) 09:03 에 처리한다
        │
monitor (08:00~09:30, 실시간 틱 판정 + 15초 유지보수)
  · **판정 주기를 동작 성격별로 분리**한다:
      - 뉴스베토·하드손절·스탑 breach **판정** → WS 틱 즉시(틱 없으면 1초 백스톱, `check_ticks`)
      - 매도 주문 **전송·재시도** → 종목별 `SELL_RETRY_COOLDOWN_SEC`(15초) 쿨다운(거부도 전송이라 카운트)
      - 트레일링 스탑 **상향** → 15초(TRAIL_PCT 가 이 주기로 튜닝된 값이라 촘촘히 하면 실효 파라미터가
        바뀐다). breach 감지는 즉시이므로 스탑선은 그대로고 청산가만 선에 붙는다
      - 유지보수(체결동기화·미체결정리) → 15초. 단 체결통보(WS `00`) 수신 시 즉시 동기화
  · 틱 판정은 DB 를 읽지 않는다 — 포지션·플랜·베토 스냅샷(`MonitorState`)은 15초 주기에만 읽고 틱은
    스냅샷+캐시 가격으로 순수 계산만 한다. 실제 매도 시점엔 `_exit_confirmed`/`execute_sell` 이 DB·브로커를
    다시 보므로 과매도로 이어지지 않는다
  · 구독 시작 시 종목별 `is_nxt_enabled` 를 1회만 조회한다
  · 판정 순서: **① 뉴스 베토(가격 무관 전량) → ② 하드 손절(HARD_STOP_LOSS_PCT, plan 유무 무관)
    → ③ 스탑/저가이탈(plan.stop_price) → ④ 트레일링 상향(TRAIL_PCT, 단조 증가)**
  · **오버나잇 US 하드손절 강화**(`US_STOP_TIGHTEN_ENABLED`): 지난밤 US 정규장 하락 강도로 하드손절 폭을
    기본에서 최대 `US_STOP_TIGHTEN_MAX` %p 좁힌다(하한 `US_STOP_MIN_PCT`, **축소 전용**). 프로세스당 1회
    계산·캐시, 취득 실패/비활성 시 기본값. 발동 시 `audit_log('monitor_us_tighten')`. ⚠️ 미검증
  · 매도 거래소는 `resolve_sell_venue()` 가 결정: 정규장(09:00~15:30)=KRX 시장가, 그 외 NXT 시간대는
    NXT 가능 종목만 NXT(최유리IOC). **NXT 불가 종목이 09:00 이전에 걸리면 매도 보류** → 09:00 이후 청산
  · **실시간 수급 관측**(`SUPPLY_FEED_ENABLED`) — **수집 전용, 판정 미사용**. 매도 발동 payload 에 그 시점
    수급 스냅샷을 붙이고, 매도 안 한 종목의 대조군으로 `SUPPLY_LOG_SEC` 주기 `monitor_supply` 를 남긴다.
    값이 없거나 낡아도, 관측이 통째로 실패해도 손절·스탑·트레일링은 완전히 동일하게 동작한다
  · ⚠️ **WS 는 항상 옵셔널**: 연결 실패·무틱·TTL(5초) 초과면 `check_once`(15초 REST 경로)가 그대로
    판정한다. `REALTIME_FEED_ENABLED=0` 으로 완전 비활성 가능
  · 하트비트(`monitor_poll`)에 ws 상태(연결·틱수·수급틱수·재연결수·마지막 틱 나이)와 `cooldown_skips` 를
    담고, 손절/스탑/베토 audit 에는 `path`(tick|slow)·`slow_wait_ms` 를 남긴다
        │
settle --venue krx (09:28) · 잔여 보유분 전량 청산(마감 데드라인) → 오버나잇 방지
        │
reconcile (20:00) · kt00018 잔고 vs 로컬 position 대조 → 드리프트 알림
```

> **현재 범위는 종가베팅 집행만**이다. 장중 상시 손절 감시·멀티 전략은 다음 단계.
> 장중매매로 넓히기 전 구조 점검은 [`docs/plan/intraday-readiness.md`](../docs/plan/intraday-readiness.md) —
> 멱등키·settle_plan PK·trade_signal 키가 "하루 1사이클"을 전제하고, 리스크 한도가 회전율을 전제하지
> 않는다는 점이 live 진입의 전제 조건으로 정리돼 있다.

**미실행 감시(dead-man's switch)**: 각 워커가 성공 완료 시 `audit_log` 에 `worker_done` 마커를 남기고,
`watchdog.py`(평일 09:35)가 핵심 워커(`settle:nxt`/`settle:krx_open`/`settle:krx`/`monitor`)의 마커
누락을 확인해 경보한다. 마커 유무만 보므로 무거래일에도 오경보가 없고, 휴장일에는 같은 거래일 가드로
함께 스킵한다. 감시 대상 추가는 `watchdog.CRITICAL_WORKERS` 에 한 줄.
watchdog 은 **jongalab 통합 스케줄러의 dead-man's switch 도 겸한다** — `job_run` 최신 `scheduled_at` 이
`SCHEDULER_STALE_HOURS`(2h) 이상 오래되면 경보.

---

## 안전장치 (구현됨)

| 장치 | 위치 | 내용 |
|---|---|---|
| 모드 | `config.py`, `execution_engine.py` | `TRADING_MODE=paper`(기본, 미전송·즉시 시뮬레이션) / `live`(실주문) |
| 글로벌 킬스위치 | env `TRADING_KILL_SWITCH=1` + DB `kill_switch` | 둘을 OR — 하나라도 켜지면 전체 차단 |
| 서킷브레이커 | `risk_engine.py` + `risk_state.py` | 일일 실현손실 ≤ -MAX_DAILY_LOSS 시 자동 킬스위치 발동 |
| 하드 한도 | `risk_engine.py` | 일일 주문수(기본 20, **매수만 카운트**). 종목당 명목금액·동시 보유종목수 상한은 제거됨(`MAX_NOTIONAL_PER_NAME`/`MAX_POSITIONS` 는 폴백 사이징 용도로만 존치) |
| 멱등키 | `execution_engine.py`, `order.py` | `YYYYMMDD:signal_id:side` UNIQUE — cron 재실행 중복 방지(거부 `:x<id>`, dead `:dead:<id>`, 부분체결 `:partial:N` 접미사로 키 해제) |
| 하드 손절 / 트레일링 | `monitor.py`, `settle_plan.py` | `HARD_STOP_LOSS_PCT` 즉시 전량(plan 유무 무관 — 보유 포지션 전부) / `TRAIL_PCT` 단조 상승 스톱(**갭상승·갭하락 잔량 plan 양쪽**. 갭상승은 초기 스탑선이 시초가 한 틱 아래라 첫 하락틱에 청산되고, 버티면 트레일링이 상승을 따라간다) |
| 종목당 시드 캡 | `seed_allocator.py` + `SEED_MAX_NAME_PCT`(0.25) | 하한가에선 손절이 물리적으로 불가하므로 **단일 종목 최악 손실은 이 캡으로만 봉쇄된다**. 고가주 첫 1주만 캡×2 이내 예외. 확신도와 무관하게 항상 적용 |
| 확신도 사이징 | `seed_allocator.conviction_from_signal`, `signal_executor.py`, `/buy-preview` + `SEED_CONVICTION_MAX_MULT`(3.0) | 표 = 매칭 selector rule 수(`rule_names`) + legacy 점수 1표(그날 점수 top-N 판정 N 은 `edge_rule.get_selected_count` — 집행 레이어 rule 의 `in_scope` 와 같은 기준). 목표금액 = `seed × 표/Σ표`. 표 없음/조회 실패 → 전원 1표 = **등가중과 완전 동일**. ⚠️ **점수 '크기' tilt 는 금지**(쓰는 건 근거의 중복 매칭 개수뿐). ⚠️ 미검증 통설 — `audit_log('seed_conviction')` 로 사후 채점, 롤백은 값 1.0 |
| 배분 대상 컷(TOP_N=10) | `seed_allocator.allocate` | 유효가 후보를 **표 수 내림차순 → 점수 내림차순**으로 정렬해 상위 10개만 배분한다. 사이징이 표 비례라 컷도 같은 자를 쓴다 — 표 많은 종목을 컷에서 떨어뜨리면 두 단계가 상충한다. 정렬 키가 클램프된 표 수라 `SEED_CONVICTION_MAX_MULT=1.0` 이면 전원 1.0 → **종전 점수순 컷으로 정확히 롤백**된다 |
| 롤링 엣지 게이트 | `regime_gate.py`, `signal_executor.py` | **기본 OFF(`REGIME_GATE_ENABLED=0`) — live 감액 없음, audit 관찰 로그만.** 재개 시 동작: 최근 `REGIME_WINDOW_DAYS` 선정종목의 점수 판별력이 역전(< `REGIME_INVERT_THRESHOLD`)이면 총 시드에 **이진 배수** `REGIME_MIN_MULT`(0.3), 아니면 1.0. 거래일 < `REGIME_MIN_DAYS`(10)면 미개입. `report_date >= REGIME_MIN_DATE` 표본만 사용 |
| 선물 환경 게이트 | `futures_gate.py`, `signal_executor.py` | **KRX·NXT(`FUTURES_GATE_VENUES`).** 매수시점 NQ 선물 + **그 시각 살아있는 코스피 선물**(KRX=주간 K200DF / NXT=야간 K200NF, 신선도 `FUTURES_STALE_SEC` 초과 시 미개입) 방향으로 배분 뒤 **종목 섹터별 keep-factor(≤1.0)** 로 수량 감액. `keep=∏_axis(1−MAX_CUT×민감도×하락강도)`, 하한 `FUTURES_SECTOR_MIN_KEEP`(0.25). 상승/보합이면 감액 없음(reduce-only). **하락강도는 축의 σ 로 정규화한 z 기준**(`FUTURES_FLAT_Z`=0.25 에서 0 ~ `FUTURES_FULL_Z`=2.0 에서 1) — 축별 σ 는 `FUTURES_SD_NQ`(0.9)·`FUTURES_SD_K200_DAY`(6.3)·`FUTURES_SD_K200_NIGHT`(1.6)·`FUTURES_SD_US_EXT`(3.0)로, 같은 %p 가 축마다 다른 사건이라 절대 %p 눈금 하나를 공유하면 주간선물 축은 하락일에 상시 최대컷이 된다. σ 는 `market_snapshot` 표준편차로 재측정해 갱신하는 값이다. 수량 적용은 `gated_shares()` 로 **반올림**(mild 컷이 1주를 0주로 없애지 않게). **결합 하한**: 레짐×선물 곱을 `SEED_COMBINED_MIN_MULT`(0.3)로 `effective_keep()` 클램프. **US 프리마켓 축은 NXT 전용**(`FUTURES_US_EXT_ENABLED`) — KRX 매수 시점엔 미국장이 폐장이라 stale. 전건 `audit_log('futures_gate')` 에 축별 σ·강도(`axes`)를 남긴다. ⚠️ 섹터 민감도·US 축은 **통설 기반 미검증**(reduce-only)이고, NQ 축은 매수시점 레벨의 예측력이 실측되지 않아 `FUTURES_NQ_MAX_CUT`(0.3)이 코스피 축(0.5)보다 낮다 |
| 거시 이벤트 게이트 | `macro_gate.py`, `signal_executor.py` | 보유 창(매수→다음 평일 09:00)의 **예정 이벤트 리스크** — futures_gate 가 실현된 방향을 재는 것과 상보적. jongalab `macro_event` 에서 창 안 이벤트를 조회해 **severity 3(FOMC·CPI·고용) 존재 시 시드 keep=`MACRO_EVENT_KEEP`(0.5)**. **sev2 는 관찰 전용**(감액 없음, 진단 기록만) — PPI·금통위에 더해 **해외 반도체 실적**(엔비디아·브로드컴·마이크론·TSMC·샌디스크)과 **관세 발효일**이 여기 들어간다. **프록시 관찰 축**(VIX·WTI·환율)도 keep 을 계산해 진단에만 기록 — ⛔ 지금 설계대로 승격 금지. 축끼리 min 결합(같은 쇼크 이중 감액 방지). 캘린더 조회 실패 시 미개입 |
| 집행 레이어 rule | `edge_execution.py`, `signal_executor.py` + risk_config `NXT_GAP_FILTER_ENABLED` | **NXT(19:50) 전용 · 원장 기반.** 주문 직전 갭을 계산해 **jongalab 원장의 live rule predicate 에 먹여** 매수 여부를 정한다(밴드는 rule 소관, 하드코딩 상수 아님). **제약 2**: ① 종목 추가 불가(화이트리스트로만 동작, 거른 몫의 시드가 논다) ② **적용 대상은 그 rule 이 혼자 데려온 종목뿐**(`in_scope` — 다른 rule 과 함께 선정·점수 top-N 포함·점수순 선정은 비대상). **fail-open 4종**(rule 없음/점수 선정분/갭 판정 불가/리포트 행 없음)이라 오설정 rule 하나가 전 종목을 막지 않는다. KRX 종가(갭 분모)·리포트 행·live rule 은 **데드라인 전** 윈도우 대기 중에 미리 확보하고, 분모는 ka10081 당일 캔들로 고정한다. 전건 `audit_log('nxt_gap_filter')` |
| 권리락 스킵 | `ex_rights.py`, `signal_executor.py`, `/buy-preview` | **다음 거래일(=이 매수분의 청산일)이 권리락일인 종목은 매수하지 않는다.** `blocklist` 다음·레버리지 치환 **전**에 원종목 기준으로 검사(조정이 일어나는 건 원종목). ⚠️ **평단 보정은 하지 않는다**(평단은 하드손절선의 기준값이라 추정 비율이 틀리면 손절선이 조용히 움직인다). 신호는 `skipped`/note=`ex_rights`. 조회 실패·캘린더 비어 있음 → **미개입**. 당일 권리락 종목은 대상 아님 |
| 뉴스 베토(악재 강제청산) | `news_veto.py`, `monitor.py` + jongalab `news_guard` | 밤사이 중대 악재 판정 종목을 monitor 가 **개장 즉시·가격 무관 전량 매도**(tag=newsveto, 가장 이른 거래소). `execute_sell` 재사용이라 멱등키·paper/live 분기 동일, 매도는 리스크 게이트 미경유(탈출 허용). 조회 실패·비활성 시 미개입 — 하드손절/스탑/09:28 백스톱 불변 |
| 레버리지 ETF 대체매수 | `leverage_map.py`, `signal_executor.py` + risk_config `LEVERAGE_ENABLED` | 토글 on 시 매수 직전 원종목을 매핑된 ETF 로 치환. 신호 id 는 그대로라 상태 갱신·멱등키·종가랩 리포트는 **원종목** 기준, 실제 주문·포지션·청산·표시는 **ETF**. 사이징·거래소 라우팅은 ETF 기준으로 재계산. 매 치환을 `audit_log('leverage_swap')`. ⚠️ 레버리지는 오버나잇 갭 손실을 배로 키우고 **시드 캡의 최악손실 방어가 실효를 잃는다** → **기본 off** |
| 실시간 피드 폴백 | `realtime_feed.py`, `kiwoom_data_client.py` | WS 캐시는 **TTL 5초**(`REALTIME_TTL_SEC`) 안의 값만 유효. 초과·무틱·미구독·다른 보드·피드 예외면 `get_fresh`→None 이라 REST 로 폴백한다. 보드(KRX/NXT)가 다르면 **다른 보드로 폴백하지 않는다** — 잘못된 보드 가격으로 손절을 판정하는 것이 값이 없는 것보다 위험. WS 스레드는 메모리 캐시만 갱신하고 DB·주문은 전부 메인 루프에서 일어난다 |
| 매도 재시도 쿨다운 | `monitor.MonitorState` | 판정은 틱 즉시지만 **주문 전송은 종목별 `SELL_RETRY_COOLDOWN_SEC`(15초) 간격**. 거부도 전송이라 성공·거부 무관하게 카운트 — 하한가 매도 거부가 초당 반복돼 유량 제한에 걸리고 정작 하한가 풀림을 놓치는 것을 막는다 |
| 죽은 주문 판정 가드 | `order_maintenance.reconcile_dead_sent`, `order.get_open_sent_aged` + `DEAD_ORDER_MIN_AGE_SEC`(60초) | 0주 체결로 소멸한 IOC 를 `canceled`+멱등키 해제로 마감하는 장치인데, 판정 기준이 소멸과 **전량체결 직후**를 구분하지 못한다. **4중 가드**: ① 전송 후 60초 미경과는 판정 보류(SQL 단계에서 제외) ② 브로커 체결내역에 체결수량이 있으면 보존 ③ 미체결로 살아있음 ④ 로컬 체결분 존재. 오판정 복구는 `order.unvoid_dead_order(id)` → 'sent' 복귀 + 멱등키 원복 후 `sync_fills` 정상 경로(값을 손으로 써넣지 않는다) |
| 대시보드 시세 스트림 격리 | `price_stream.py`, `api /monitor/stream` | **표시 전용** — 주문·손절 판정을 경유하지 않고 스레드는 스냅샷 메모리만 갱신한다. WS 세션은 모니터 탭 구독자가 있는 동안만 살아 있다(30초 유예). 스트림이 죽거나 `PRICE_STREAM_ENABLED=0` 이면 종전 15초 폴링으로 동작하고, 남은 스냅샷은 `fresh_prices()` 신선도(5초)로 걸러진다 |
| 불변 감사로그 | `audit_log.py` | append-only(UPDATE/DELETE 없음) |
| 블록리스트 | `blocklist.py`, `signal_executor.py` | 자동매매 제외 종목(수동 보유분). **수동 매수한 종목은 즉시 등록**한다 |
| 정합성 점검 | `reconcile.py` | 매일 브로커 잔고 vs 로컬 포지션 대조 — **감지·알림만 하고 자동 교정은 하지 않는다** |
| 미실행 감시 | `watchdog.py` + `audit_log` worker_done | 위 흐름 말미 참고 |

튜닝 파라미터(`config.py`): `STOP_BUFFER_PCT`(**갭하락 전용** 버퍼 — 갭상승 스탑선은 파라미터가 아니라
`시초가−1원`(한 틱) 고정이다) · `TRAIL_PCT`(트레일링, 15초 주기 기준으로
튜닝된 값) · `HARD_STOP_LOSS_PCT`(하드 손절) · `FUTURES_SD_*`(선물 게이트 축별 σ — 이 값이 강도 눈금의
기준이라 시장 변동성 레짐이 바뀌면 재측정 대상) · `FUTURES_FLAT_BAND`/`FUTURES_FULL_CUT_PCT`(이 둘은
**monitor 의 US 정규장 손절 강화 축 전용** — 선물 게이트는 σ 기준으로 옮겼다) · `SEED_MAX_NAME_PCT`(종목당 시드 캡) ·
`SEED_CONVICTION_MAX_MULT`(확신도 상한, 1.0=off) · `SUPPLY_FEED_ENABLED`/`SUPPLY_LOG_SEC`(수급 관측 —
끄고 켜도 매매 동작 불변).

---

## 프론트엔드 (`frontend/`, :3001)

홈(당일 손익·매수·보유·매수 프리뷰) · 모니터(워커 하트비트·활성 플랜) · 히스토리(월/일 주문) ·
캘린더(월간 손익) · 설정(킬스위치·리스크 한도·블록리스트·레버리지 ETF). 관리자 비밀번호 로그인(httpOnly 쿠키).

**모니터 탭 실시간 시세(SSE)**: `GET /monitor/stream`(`core/price_stream.py`) → Next 프록시 → 브라우저
`EventSource`(`useLivePrices`). 1초마다 바뀐 것만 보내고 15초 무변화면 `: ping`.
- **가격만 보낸다.** 스탑선·활동 로그·주문은 계속 15초 `/monitor` 폴링이 출처다(표시용 스트림이 자금 경로
  상태의 출처가 되지 않게). 프론트는 폴링 스냅샷 위에 가격만 덮어쓰고 평가금액·미실현손익을 재계산한다.
- **구독자가 있을 때만 WS 세션이 산다**(refcount + `PRICE_STREAM_IDLE_SEC`=30초). 탭이 백그라운드로 가면
  끊고 돌아오면 붙는다. ⚠️ 같은 토큰으로 워커 세션과 동시에 살 때 양쪽이 다 틱을 받는지는 **미검증**
  ([`docs/plan/realtime-ws-migration.md`](../docs/plan/realtime-ws-migration.md) §2.1)이라 겹치는 시간을
  '탭을 보는 동안'으로 한정했다. 이상 시 `PRICE_STREAM_ENABLED=0`.
- 틱이 없는 종목·시간은 종목당 `PRICE_STREAM_REST_TTL_SEC`(15초) REST 폴백이고, '실시간' 뱃지는 WS 틱이
  10초 안에 들어올 때만 붙는다.

**거시 이벤트 표시**(`GET /macro-events?month=YYYYMM`): 캘린더 탭 날짜 셀 점 마커(주황=sev3 감액 대상 /
회색=sev2 관찰) + 범례 + 상세 뱃지. 홈 '오늘 매수 예정' 카드는 `/buy-preview` 의 `macro` 진단으로
오늘 밤 이벤트를 안내한다(레짐 축소도 같은 자리).

**윈도우 종료 표시**(`/buy-preview` 응답 `venues[].closed`): 데드라인이 지난 거래소는 `closed=true` ·
**시드·수량 0 · note=`윈도우 종료`**(배분·게이트 조회도 건너뜀). 표시 계층만 — 거래소별 시드는 여전히
전체 점수합으로 나눈다.

**반복 거부/취소 표시 병합**: 히스토리 탭은 같은 날 (종목·방향·상태)가 같은 rejected/canceled 행을
한 줄로 묶어 "거부 ×238 · 08:17~09:30"로 보여준다(`collapseRepeats`, 표시 전용 — API/DB·재시도 동작 무변경).

**미체결 사유**: `GET /orders` 응답의 `reason`. 거부는 키움 거부 메시지(코드 래퍼 제거), 그 외는 상태 기반
일반 사유. 주문 행이 안 생기는 **매수 스킵/차단**도 `month` 조회 시 order 와 같은 모양
(`status='skipped'`, `kind='skip'`)으로 만들어 시간순으로 섞는다.

**청산 종목 워커 로그**: 청산 목록에서 종목을 누르면 ① **1분봉 차트**(`GET /stock-chart` — 정규장은 KRX 봉,
그 밖은 NXT(`{stk_cd}_NX`) 봉으로 **합본**, 분 단위 중복은 KRX 우선. `lightweight-charts` 가 야간 공백을
접는다) ② **워커 활동 트레일**(`GET /stock-events`, 라벨 렌더링은 모니터 탭과 `lib/events.ts` 공유).
구간은 매수날≠매도날이면 **매수날 15:00~매도날 10:00**(한 사이클을 감싼다). 단 1회 매수를 여러 날 나눠
판 분할/이월 청산이면 뒤 매도일은 **매도 당일만** 본다. 매수처 짝짓기는 order 매수 + **수동 매수**
(`manual_buy_link`)를 합쳐 매도일 직전 최신 매수를 고른다(수동 분은 order 테이블에 없어 이게 없으면
엉뚱한 옛 매수에 묶인다).

---

## 기동
```bash
uv run --directory trading uvicorn api:app --host 127.0.0.1 --port 8002   # API
cd trading/frontend && npm run dev                                        # 대시보드(:3001)
```

## 테스트 (자금 경로)
`tests/` 는 자금 손실에 직결되는 순수 로직의 동작을 **DB·키움 네트워크 없이** 고정한다
(fake 협력 객체 주입 + repository monkeypatch). 커버리지:
- 시드 배분(`seed_allocator`) — 캡·첫1주 예외·확신도 표 비례·클램프·표 없으면 등가중 동일·표 계산법
- 멱등키·사이징·paper 체결 시뮬레이션(`execution_engine`), 한도·서킷브레이커 분기(`risk_engine`)
- 게이트 — 레짐 배수 매핑·역전 판정 / 선물 섹터 클래스·keep 차등·미개입 / 거시 보유 창·severity·프록시
  관찰 전용·미개입
- 뉴스 베토 — 전량매도·0순위 우선·fail-safe(빈 판정/조회 실패에도 하드손절 정상)·venue 보류·TTL 캐시
- 집행 레이어 rule — 레이어 감지·fail-open 4종·점수 선정분 불개입·오설정 rule 격리·행 비변형·
  밴드는 predicate 소관 / NXT 갭 산식 / **predicate 복제 드리프트**(jongalab 원본과 op·NULL 규약·AND
  결합이 어긋나면 '측정한 것과 다른 것을 산다')
- 레버리지 치환 순수 로직 · 죽은 주문 판정 가드 4종 · 시초가 단계 분기(방향 무관 절반+plan, 스탑선만
  갈림 — 갭상승=시초가−1틱 / 갭하락=시초가−버퍼)
- 실시간 피드 — TTL/미구독/다른 보드/예외 → REST 폴백, 부호 붙은 현재가 절대값 파싱, 체결통보 1회 소비,
  등록 상한 캡, **틱 경로는 하드손절 즉시 집행하되 트레일링 상향은 안 함**, 쿨다운 억제·경과 후 재시도,
  체결 확인 시 스냅샷 제거, **수급 관측이 판정에 개입하지 않음**

민감 파일(`risk_engine.py`·`execution_engine.py`)은 **수정하지 않고 동작만 핀**한다.
```bash
uv run --directory trading --group dev pytest
```

## 유지보수
1. 5가지 사전 검토(필요성·기존 코드·최단 구조·최소 혼란 흐름·유지보수성) 후 착수.
2. 변경 전 이 README 로 흐름·안전장치를 파악하고 [`docs/history/`](../docs/history/) 의 해당 축 파일로
   이미 기각된 방향을 확인한다. 변경 후엔 이 README 의 **현재 상태**를 갱신하고 **판정 근거·수치는
   `docs/history/`** 에 남긴다.
3. `risk_engine.py`·`execution_engine.py` 는 사용자 확인 없이 수정 금지.
4. 검증: `uv run --directory trading python -m py_compile <file>`, `paper` 모드로 동작 확인 후 보고.
   자금 경로를 건드렸으면 위 pytest 를 변경 전·후로 돌린다.
