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

### `trade_signal` 계약
jongalab→trading 유일한 결합점. trading 은 `trade_date·stk_cd·stk_nm·rank_no·score·status` 를 읽어
집행한다. `rule_names`(nullable, 2026-07-04 추가) 는 **선정 근거 edge_rule name 콤마 목록**으로
jongalab 이 채우지만 **trading 도메인은 읽지 않는다**(하위호환 — risk_engine·execution_engine·
seed_allocator 무변경). 실현손익→가설 귀속은 jongalab 이 `trade_signal ⨝ audit_log/fill` 로 계산.
NULL = legacy 점수 선정(rule 미태깅). rules 모드 무거래일엔 신호 자체가 없다.

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
│   ├── seed_allocator.py       # 시드 배분(거래소별): 상위10 선정(점수순)·등가중 배분·최소투입 우선 그리디·종목당 시드 25% 캡(고가주 첫 1주만 캡×2 이내 예외 — 2026-07-10 HLB 하한가 사건으로 50%→25%, .env SEED_MAX_NAME_PCT)
│   ├── regime_gate.py          # 롤링 엣지 게이트: 최근 선정종목 점수판별력(익일시가 상위½−하위½)이 역전이면 총 시드 축소(이진 배수) — 2026-07-23 기본 OFF(관찰 로그만)
│   ├── futures_gate.py         # 선물 환경 게이트(KRX·NXT): 매수시점 NQ+코스피선물(KRX=주간/NXT=야간) 하락 시 섹터별 차등 감액(반도체·IT 더, 방어주 덜). NXT 는 US 장 마감 후 최근 등락(프리마켓 SOXX·SKHY·EWY·KORU, /api/us-extended) 축도 추가
│   ├── macro_gate.py           # 거시 이벤트 게이트: 보유 창(매수→익일 시가)에 sev3 예정 이벤트(FOMC·CPI·고용, jongalab macro_event)가 있으면 시드 keep 축소 + VIX·WTI·환율 프록시 관찰
│   ├── news_veto.py            # 뉴스 베토 조회: jongalab news_veto_verdict(severe=1, 밤사이 중대 악재 판정) 읽기 전용 — monitor 가 해당 종목 개장 즉시 전량매도. 실패 시 미개입, 60s TTL 캐시
│   ├── market_calendar.py      # 거래일 판별(jongalab 복제): XKRX 달력 + EXTRA_HOLIDAYS 수동 오버라이드. 모든 워커가 진입부에서 휴장일이면 exit 0 (2026-07-17 제헌절 휴장일 오실행 사고 재발 방지 — 달력에 없는 신규 공휴일은 jongalab 쪽과 함께 추가)
│   ├── kiwoom_order_client.py  # 키움 REST 직접 호출(kt10000~3 주문, kt00018 잔고, ka10074~6)
│   ├── kiwoom_data_client.py   # kiwoom 데이터 서버(:8001) 읽기(현재가·NXT·차트) + 실시간 피드 캐시 우선(attach_feed)
│   ├── realtime_feed.py        # 키움 WS 실시간 구독(0B 주식체결 · 00 주문체결통보). 백그라운드 스레드가 메모리 캐시만 갱신하고 DB·주문은 전부 호출부에서. **항상 옵셔널** — 끊김·무틱·TTL 초과 시 REST 폴백
│   ├── fill_sync.py            # 실거래 체결 동기화(ka10076 → fill/position)
│   ├── order_maintenance.py    # 스테일 주문 취소·미체결(dead) 정리
│   ├── position_manager.py     # 포지션 조회·평가손익(청산 후보는 미구현)
│   ├── notifications.py        # 텔레그램 관리자 알림
│   └── repository/             # DB 접근 계층
│       ├── trade_signal.py     # jongalab 신호 수신(pending→done)
│       ├── order.py            # 주문 의도/전송 추적 + 멱등키
│       ├── fill.py             # 체결 기록(수량·가격·수수료·세금)
│       ├── position.py         # 보유 포지션(평단·실현손익)
│       ├── settle_plan.py      # 청산 계획(stop_price, 트레일링) — 2026-08-03 이후 **갭하락 잔량만** 생성
│       ├── risk_state.py       # 일자별 상태(주문수·실현손익·브레이커)
│       ├── risk_config.py      # 리스크 한도 + 최초 시드 배율(SEED_INIT_MULT, JSON, 대시보드 편집)
│       ├── blocklist.py        # 자동매매 제외 종목(수동 보유분)
│       ├── leverage_map.py     # 레버리지 ETF 대체매수 매핑(원종목→ETF, 대시보드 편집)
│       ├── audit_log.py        # 불변 append-only 이벤트 로그
│       └── kiwoom_token.py     # 공유 토큰 읽기 전용
├── workers/                    # PM2 cron (스케줄은 루트 ecosystem.config.js). 전 워커가 진입부에서 휴장일 차단(core/market_calendar)
├── frontend/                   # Next.js 대시보드(:3001)
├── sql/                        # trading DB 스키마
└── tests/                      # 자금 경로 단위 테스트 (pytest, DB/네트워크 없이 fake 주입)
```

---

## 집행 흐름 (신호 → 체결 → 청산 → 정합성)

종가베팅 1사이클을 거래소(KRX/NXT)별로 집행한다.

```
[jongalab closing_bet] → trade_signal(pending)
        │   ※ closing_bet 은 30분마다 재실행되며 그때 후보에서 빠진 잔여 pending 을 expired 로 정리한다.
        │     따라서 **jongalab 쪽 veto 는 자금 경로 코드 없이 NXT 매수를 취소한다** — 특히 2026-07-28 도입한
        │     공시 veto(veto_disclosure_severe)는 장 마감 후 공시(15:30~18:00)를 19:00 재실행에 반영해
        │     19:30 NXT 매수 대상에서 떨군다. KRX 15:20 기체결분은 되돌릴 수 없어 익일 news_guard 담당.
        │
signal_executor (KRX 15:00 / NXT 19:30)
  · 블록리스트 제외 → 거래소 분류 → 시드 산정 → **최초 시드 배율(risk_config `SEED_INIT_MULT`, 게이트보다 먼저)** → **regime_gate(역전 레짐)로 총 시드 축소 — 2026-07-23 기본 OFF(미개입 1.0), audit 관찰만** → seed_allocator 등가중 배분 → **futures_gate(선물 하락 시 섹터별 수량 감액, KRX·NXT) × macro_gate(보유 창 sev3 예정 이벤트 시 공통 감액)**
  · 매수 타이밍은 **종가 단일 매수** — 윈도우 시작에 수량을 확정하고 데드라인(15:20 KRX 동시호가 / 19:50 NXT IOC)에 전 종목 매수. 윈도우 동안은 하트비트만(대시보드 가동 표시). closing_bet 엣지가 종가→익일시가로 측정·검증되므로 진입가를 종가에 맞춘다(과거 '눌림 추종'은 2026-07-20 실거래 표본에서 데드라인 대비 평균 −0.27%·KRX −0.44% 손해로 제거)
  · NXT 는 최유리 IOC 특성상 부분체결 가능 — 주문 직후 ka10076 체결내역으로 목표 수량 대비 체결량을 확인하고,
    체결 row 가 확인된 부분체결이면 19:50 전 잔량을 최대 2회 별도 멱등키(`:partial:N`)로 재시도한다
    (체결내역이 아직 안 보이면 과매수 방지를 위해 재시도하지 않고 19:55 fills_sync/알림에서 미체결로 드러나게 둔다)
  · **체결통보(WS `00`)로 대기 단축**(2026-07-31): 데드라인 집행 직전에 체결통보만 구독(`_start_fill_feed`,
    시세 0B 는 구독 안 함)하고, 고정 3초 대기 대신 통보를 기다린다(오면 즉시). 통보를 받았는데 ka10076 이
    아직 반영 전이면 0.5초 뒤 한 번 더 조회한다 — 종전엔 이 경우를 '체결내역 미확인'으로 보고 재시도를
    포기해 잔량을 놓쳤다. 구독 실패·통보 미수신이면 종전 고정 대기와 완전히 동일하게 동작한다.
  · 마감 시각(데드라인)에 전 종목 시장가/IOC 집행 → 신호 status 갱신(done/skipped/rejected)
  · 주문 직전 live 주문가능금액(100stk_ord_alow_amt) 재조회로 수량 보정 — 시드는 윈도우 시작
    1회 스냅샷이라, 앞선 종목 체결·증거금 선반영으로 줄어든 현금에 마지막 종목이 '증거금
    부족'으로 통째 거부되지 않도록 살 수 있는 최대 수량으로 축소(0이면 스킵)한다(execution_engine).
        │
fills_sync (15:31 / 19:55) · ka10076 체결 동기화 → position 갱신 + 매수 텔레그램 알림
        │
settle --venue nxt (08:03)      · NXT 상장 종목: NXT 시초가로 갭 판정 (tag=nxt)
settle --venue krx_open (09:03) · NXT 미상장 종목: KRX 개장가로 갭 판정 (tag=krxopen)
  · **갭상승 → 전량 매도, settle_plan 없음 / 갭하락 → 절반 매도 + 저가이탈선(시초가−STOP_BUFFER_PCT) plan 생성**
  · 갭상승 잔량 폐지 근거(2026-08-03 실체결 66건, 6/19~8/3): 종전 갭상승 스탑선은 '절반매도 체결가·버퍼 0'
    이라 첫 하락틱에 걸려 **보유 중앙값 0분**(5분 내 56/66)에 시장가/IOC 로 스탑선보다 몇 틱 아래 체결됐다 —
    잔량이 절반매도가보다 싸게 팔린 게 **65/66건**(평균 −0.49%), 트레일링이 상승을 실제로 따라간 건 1건뿐.
    "시초가에 전량" 반사실이 잔량 +0.52%p·**포지션 +0.45%p/건(t=3.35)**, 기간·단계 분할 모두 양수.
    초기 스탑 버퍼(0.5~3%)·트레일 완화·갭 크기 조건부는 전부 무효~마이너스 → 여유를 주는 게 아니라
    잔량을 없애는 쪽이 개선. **갭하락은 부호가 반대**(버퍼 후 회복 대기가 즉시 전량보다 +0.78%p 유리, n=26)라 무변경.
    같은 표본에서 '더 오래 보유'(09:28 −1.21%p / 15:20 −2.46%p)는 아웃샘플에서도 재기각.
  · 두 단계는 동일 전략(_run_open_stage 공용). 대상 종목 집합·거래소(NXT 최유리IOC / KRX 시장가)·tag 만 다르다.
  · NXT 미상장 종목은 NXT 호가가 없어 08:03 를 건너뛰고, KRX 정규장 개장(워밍업 후) 09:03 에 처리한다.
  · 집행 시각 :03 근거(실측): NXT 는 프리마켓 갭상승이 첫 5분간 식어 08:03 이 08:05 대비 평균 +0.35%
    (08:00~08:01 은 얇은 단발 호가 허수가 끼어 제외). KRX 불가 종목은 개장 드리프트가 없어(평균 ≈0%)
    시점 중립이라 :03 으로 통일. KRX 상장 종목과 달리 NXT 불가 종목엔 "1분이 더 높다"가 성립하지 않는다.
monitor (08:00~09:30, 실시간 틱 판정 + 15초 유지보수 — 2026-07-31 WS 전환)
  · **판정 주기를 동작 성격별로 분리**한다. 손절 판정은 지연이 곧 손실이라 틱 즉시로 올리고,
    주문 전송·트레일링 상향·유지보수는 기존 15초 주기를 유지한다:
      - 뉴스베토·하드손절·스탑 breach **판정** → WS 틱 즉시(틱 없으면 1초 백스톱, `check_ticks`)
        근거: 15초 폴링은 노이즈 필터가 아니라 **무작위 샘플링**이다 — 진짜 하락이면 손절선보다
        낮은 가격에 팔리고(확실한 손실), 순간 급락이면 운에 맡긴다. 2026-07-18 백테스트에서
        '확인틱'(지연 추가)이 현행보다 나빴던 것과 같은 방향이고, 그 백테스트는 1분봉이라
        15초/1초를 애초에 구분할 수 없었다.
      - 매도 주문 **전송·재시도** → 종목별 15초 쿨다운(`SELL_RETRY_COOLDOWN_SEC`).
        2026-07-10 HLB 하한가 때 15초 주기로도 거부가 238건 쌓였다. 판정 주기를 그대로 주문에
        물리면 시간당 수천 건이 되어 키움 유량 제한에 걸리고 하한가 풀림을 놓친다. 재시도 자체는
        유지(백오프 기각 결정 불변)하되 간격만 종전 폴링 주기로 고정한다. 거부도 전송이라 성공·거부 무관하게 카운트.
      - 트레일링 스탑 **상향** → 15초(기존). TRAIL_PCT=0.75 는 15초 주기 백테스트로 튜닝된 값이라,
        상향을 촘촘히 하면 실효 TRAIL_PCT 가 좁아져(비채택된 0.5 쪽으로) 파라미터가 무단 변경된다.
        **breach 감지는 즉시**이므로 스탑선은 그대로 두고 청산가만 선에 붙는다(순 개선).
      - 유지보수(체결동기화·미체결정리) → 15초. 단 **체결통보(WS `00`) 수신 시 즉시** 동기화.
  · 틱 판정은 DB 를 읽지 않는다 — 포지션·플랜·베토 스냅샷(`MonitorState`)은 15초 주기에만 읽고
    틱은 스냅샷+캐시 가격으로 순수 계산만 한다(삼성전자 단독 32틱/초라 틱마다 DB 조회는 불가).
    실제 매도 시점엔 `_exit_confirmed`/`execute_sell` 이 DB·브로커를 다시 보므로 과매도로 이어지지 않는다.
  · 구독 시작 시 종목별 `is_nxt_enabled` 를 **1회만** 조회한다 → 폴링마다 반복하던 ka10100 호출이 사라진다.
  · ⚠️ **WS 는 항상 옵셔널**: 연결 실패·무틱·TTL(5초) 초과면 `check_once`(15초 REST 경로)가 그대로
    판정하므로 WS 가 죽어도 종전 동작이 유지된다. `REALTIME_FEED_ENABLED=0` 으로 완전 비활성 가능.
  · 하트비트(`monitor_poll`)에 `ws` 상태(연결·틱수·재연결수·마지막 틱 나이)와 `cooldown_skips` 를 담아
    대시보드에서 피드 가동 여부를 확인한다. 손절/스탑/베토 audit 에는 `path`(tick|slow)와
    `slow_wait_ms`(15초 폴링이었다면 더 기다렸을 시간)를 남겨 **즉시 판정의 실이득을 사후 채점**한다.
  · **0순위 뉴스 베토**: jongalab news_guard(07:00~09:25)가 밤사이 중대 악재(FDA 불승인·계약 파기류)로
    판정한 종목(news_veto_verdict severe=1)은 **가격 무관 즉시 전량 매도**(tag=newsveto) — 하드손절보다
    앞이라 갭이 가격에 반영되기 전에도 탈출. 매도 전송 성공 시 관리자 텔레그램, 체결 확인 후 plan 해제.
    조회 실패/비활성(NEWS_VETO_ENABLED)이면 미개입(core/news_veto.py, 60s 캐시) — 아래 백스톱 불변.
  · 하드 손절(HARD_STOP_LOSS_PCT) · 트레일링 스톱(TRAIL_PCT, 단조 상승) → 돌파 시 전량 매도(tag=stop)
  · **오버나잇 US 하드손절 강화(`US_STOP_TIGHTEN_ENABLED`)**: KRX 종가베팅 보유분은 매수(15:20) 시점 미국장이
    다크라 futures_gate 의 US 확장 축을 못 받는다. 대신 monitor(08:01~)엔 지난밤 미국 정규장이 이미 마감 →
    `/api/us-extended` 의 `regular_ret`(반도체 min(SOXX,SKHY) + 한국 min(EWY,KORU/3))로 오버나잇 하락 강도를
    재, 급락 밤이면 하드손절 폭을 기본(HARD_STOP_LOSS_PCT)에서 최대 US_STOP_TIGHTEN_MAX %p 좁힌다(하한
    US_STOP_MIN_PCT, 축소 전용). 프로세스당 1회 계산·캐시(오버나잇 결과는 아침 내내 고정), 취득 실패/비활성
    시 기본값 미개입. 발동 시 audit_log(`monitor_us_tighten`). ⚠️ 미검증(통설, reduce-only)
  · 매도 거래소는 `resolve_sell_venue()`가 시각+NXT여부로 결정: 정규장(09:00~15:30)=KRX 시장가, 그 외 NXT 시간대는 NXT 가능 종목만 NXT(최유리IOC). **NXT 불가 종목이 09:00 이전에 손절/스탑에 걸리면 매도 보류**(NXT 주문은 키움에서 거부되고 KRX는 개장 전) → 09:00 KRX 개장 후 폴링에서 청산. is_nxt_enabled 는 발동 시점에만 조회(실패 시 보수적 보류, 다음 폴링서 자가복구)
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
휴장일에는 워커들이 진입부에서 스킵되어 마커가 안 남으므로 watchdog 도 같은 거래일 가드로 함께 스킵한다(오경보 방지).
watchdog 은 **jongalab 통합 스케줄러의 dead-man's switch 도 겸한다**: jongalab `job_run` 의 최신
`scheduled_at` 이 2시간(`SCHEDULER_STALE_HOURS`) 이상 오래되면 스케줄러 중단으로 보고 경보한다
(youtube_collector 가 15분 주기라 살아있으면 항상 신선 — 2026-07-15 배포 훅 재시작 끊김으로 이틀 무감지 중단된 사고 재발 감지).

---

## 안전장치 (구현됨)
| 장치 | 위치 | 내용 |
|---|---|---|
| 모드 | `config.py`, `execution_engine.py` | `TRADING_MODE=paper`(기본, 미전송·즉시 시뮬레이션) / `live`(실주문) |
| 글로벌 킬스위치 | env `TRADING_KILL_SWITCH=1` + DB `kill_switch` | 둘을 OR — 하나라도 켜지면 전체 차단 |
| 서킷브레이커 | `risk_engine.py` + `risk_state.py` | 일일 실현손실 ≤ -MAX_DAILY_LOSS 시 자동 킬스위치 발동 |
| 하드 한도 | `risk_engine.py` | 일일 주문수(기본 20, **매수만 카운트** — 청산 매도는 제외). 종목당 명목금액·동시 보유종목수 상한은 제거됨(상위 종목 집중 배분을 위해 — `MAX_NOTIONAL_PER_NAME`/`MAX_POSITIONS` 는 `execution_engine` 폴백 사이징 용도로만 존치) |
| 멱등키 | `execution_engine.py`, `order.py` | `YYYYMMDD:signal_id:side` UNIQUE — cron 재실행 중복 방지(거부 `:x<id>`, dead `:dead:<id>` 접미사로 키 해제 — id 로 고유성 보장) |
| 하드 손절 / 트레일링 | `monitor.py`, `settle_plan.py` | HARD_STOP_LOSS_PCT 즉시 전량(plan 유무 무관 — 보유 포지션 전부) / TRAIL_PCT 단조 상승 스톱(**갭하락 잔량 plan 에만 해당** — 갭상승은 2026-08-03 부터 시초가 전량매도라 잔량이 없다). 지난밤 US 정규장 급락이면 하드손절 폭을 보수적으로 좁힘(`US_STOP_TIGHTEN_ENABLED`, 위 monitor 흐름) |
| 실시간 피드 폴백 | `realtime_feed.py`, `kiwoom_data_client.py` | WS 캐시는 **TTL 5초**(`REALTIME_TTL_SEC`) 안의 값만 유효. 초과·무틱·미구독·다른 보드·피드 예외면 `get_fresh`→None 이라 기존 REST 경로로 폴백한다. 보드(KRX/NXT)가 다르면 **다른 보드로 폴백하지 않는다** — 잘못된 보드 가격으로 손절을 판정하는 것이 값이 없는 것보다 위험. 조용히 끊긴 WS 의 stale 가격으로 손절이 미발동하는 최악 실패를 이 TTL 하나가 막는다. WS 스레드는 메모리 캐시만 갱신하고 DB·주문은 전부 메인 루프에서 일어난다(재진입·락 없음) |
| 매도 재시도 쿨다운 | `monitor.MonitorState` | 판정은 틱 즉시지만 **주문 전송은 종목별 `SELL_RETRY_COOLDOWN_SEC`(15초) 간격**. 거부도 전송이라 성공·거부 무관하게 카운트. 하한가 매도 거부가 초당 반복돼 유량 제한에 걸리고 정작 하한가 풀림을 놓치는 것을 막는다(2026-07-10 HLB 238건 → 초당 재시도면 시간당 수천 건) |
| 불변 감사로그 | `audit_log.py` | append-only(UPDATE/DELETE 없음) |
| 블록리스트 | `blocklist.py`, `signal_executor.py` | 수동 보유 종목 자동매수 차단 |
| 레버리지 ETF 대체매수 | `leverage_map.py`, `signal_executor.py` + risk_config `LEVERAGE_ENABLED` | 토글 on 시 signal_executor 가 매수 직전(**blocklist 제외 후·`is_nxt_enabled` 조회 전**) 원종목을 매핑된 레버리지 ETF 로 치환(`resolve_leverage_target`). 신호 id 는 그대로라 상태 갱신·멱등키·종가랩 리포트는 **원종목** 기준, 실제 주문·포지션·청산·이 대시보드 표시는 **ETF**(ETF 는 시그널에 안 남으므로 `/names` 가 `leverage_map` 의 `etf_stk_nm` 을 합쳐 코드 대신 이름으로 표시). 사이징은 ETF 현재가로 재계산되고, 거래소 라우팅도 ETF 의 NXT 여부로 결정된다(원종목이 NXT 가능이어도 ETF 가 NXT 불가면 KRX 종가 15:20 매수). 매 치환을 `audit_log('leverage_swap')` 기록. `/buy-preview` 도 동일 치환(매수 예정에 ETF 표시). ⚠️ **레버리지는 오버나잇 갭 손실을 배로 키우고 종목당 시드 25% 캡의 최악손실 방어가 실효를 잃는다**(ETF 는 그 종목이 아니라 신호 엣지도 근사) — 손실 최소화 목표와 상충하므로 기본 토글 off |
| 롤링 엣지 게이트 | `regime_gate.py`, `signal_executor.py` | **⚠️ 2026-07-23 기본 OFF(`REGIME_GATE_ENABLED=0`) — live 감액 중단, audit 관찰 로그만 유지.** 사유: 임계 0은 점수가 양의 엣지를 갖던 구로직(전체 스프레드 +1.13%p)에 맞춘 값인데 스코어/선정 로직 변경 후로는 스프레드가 상시 음수(6/26 −1.14%p, 7/07 −1.55%p)라 "역전"이 평상시 기본값 = 등가중 전환 근거(점수의 익일손익 예측 실패/역상관)와 같은 횡단면 현상을 총노출 신호로 오인, 수익 나는 날에도 상시 30% 컷(7/23 첫 실발동). 재개하려면 env=1. 이하 로직은 재개 시 동작: 최근 REGIME_WINDOW_DAYS 선정종목의 점수 판별력(익일시가 상위½−하위½ 스프레드)이 역전(split < REGIME_INVERT_THRESHOLD, 기본 0)이면 총 시드에 **이진 배수** REGIME_MIN_MULT(기본 0.3) 적용, 아니면 1.0 — 2026-07-14 백테스트(4/9~7/10 60판단일)에서 역전 '깊이'가 다음날 성적과 무상관(강한 역전일 +0.36% > 약한 축소일 −0.18%)이라 선형 램프를 이진으로 대체. jongalab `daily_stock_report.next_open_ret` 읽기전용 조회(단 `report_date >= REGIME_MIN_DATE` 만 — 그 이전은 구 스코어 로직이라 제외), **거래일 < REGIME_MIN_DAYS(기본 10)면 미개입(1.0)** — 종목-일 표본은 같은 날 시장 무브로 상관되어 거래일이 실효 표본(edge_policy PROMO_MIN_DAYS 와 동일 논리, 구 '종목-일 30개' 기준은 실효 4거래일로 최대 축소가 나가는 문제로 대체). **매 판단(미개입 포함)을 `audit_log('regime_gate')`에 기록**해 게이트 성적을 사후 채점 가능 → 모니터 탭 활동 피드에 사유 노출. `/buy-preview`(매수 예정)도 동일 배수로 시드를 미리 반영·표시 |
| 선물 환경 게이트(섹터 차등) | `futures_gate.py`, `signal_executor.py` | **KRX·NXT(`FUTURES_GATE_VENUES`).** 매수시점 NQ 선물(jongalab market-indices) + 코스피200 선물 방향으로. **코스피 축은 그 시각 살아있는 선물**: KRX(15:20)=주간선물(K200DF, market-indices 실시간) / NXT(19:50)=야간선물(K200NF, jongalab DB `kis_night_future`, 신선도 FUTURES_STALE_SEC 초과 시 미개입). seed_allocator 등가중 배분 뒤 **종목 섹터(키움 업종명, `ticker_dictionary`)별 keep-factor(≤1.0)로 수량 감액**. 섹터 클래스별 축 민감도: 반도체·IT(NQ 민감)·경기민감주(자동차·화학·금융, 지수 민감)를 더 깎고 통신·음식료 등 방어주를 덜 깎음. `keep=∏_axis(1−MAX_CUT×민감도×하락강도)`, 하락강도는 폭 비례(-FUTURES_FLAT_BAND=0 ~ -FUTURES_FULL_CUT_PCT=1) — 작은 하락(NQ -0.5%)은 살짝, 급락(-2%+)은 최대컷. 하한 FUTURES_SECTOR_MIN_KEEP(0.25). 상승/보합이면 감액 없음(reduce-only). 수량 적용은 `gated_shares()` 로 **반올림**(내림 아님) — mild 컷(keep≥0.5)이 1주짜리를 0주로 없애지 않도록(keep<0.5 만 0 가능). **결합 하한**: 레짐×선물 곱이 SEED_COMBINED_MIN_MULT(0.3) 밑으로 안 내려가게 종목 keep 을 `effective_keep()` 로 클램프(REGIME_MIN_MULT>=이 값이어야 보장, 기본 둘 다 0.3). 지표 취득 실패면 미개입. **US 장 마감 후 최근 등락 축(NXT 전용, `FUTURES_US_EXT_ENABLED`)**: NXT(19:50)는 매수 시점 미국 프리마켓이 열려 있어 jongalab `/api/us-extended`(SOXX·SKHY·EWY·KORU)의 `extended_ret`(정규장 종가 대비 프리마켓 최근 등락)을 순방향 신호로 추가한다 — 미국 정규장 '일일 등락'은 지난밤 세션이라 이미 국장 종가에 반영(후행)이라 안 쓴다. 반도체 min(SOXX,SKHY)는 tech 클래스만, 한국 min(EWY,KORU/3, 3x 정규화)은 idx 민감도로 전 섹터에 `FUTURES_US_EXT_MAX_CUT`(0.3) 로 곱한다. **KRX(15:20)는 매수 시점 미국장이 완전 폐장(다크)이라 확장 데이터가 stale → 이 축 미개입**(선물 축만); 시장 상태가 프리마켓/정규장 아니면(애프터·폐장) NXT 라도 미개입. 매 적용을 audit_log(`futures_gate`)에 선물값+US 확장(semis/korea/market_state)+섹터별 keep 스냅샷으로 기록 → 모니터 탭 활동 피드에 사유(NQ·코스피선물 등락, 감액 종목수·섹터) 노출. `/buy-preview`도 동일 로직으로 예상 수량을 미리 감액·표시(NXT 는 야간세션 개장 전이면 미개입·"대기" 표기). ⚠️ **섹터 민감도·US 확장 축은 통설 기반 미검증 가정(reduce-only)** — 추후 stk_cd→섹터 조인·US 확장 표본으로 실측 후 재튜닝 |
| 거시 이벤트 게이트 | `macro_gate.py`, `signal_executor.py` | **보유 창(매수→다음 평일 09:00)의 '예정 이벤트 리스크'** — futures_gate 가 이미 실현된 선물 방향을 재는 것과 상보적(발표 전엔 선물이 보합이라 저건 못 잡음). jongalab DB `macro_event`(수동 시드 캘린더, `sql/18. migrate_macro_event.sql`, 2026 연말까지 시드)에서 창 안 이벤트를 조회해 **severity 3(FOMC·CPI·고용) 존재 시 시드 keep=MACRO_EVENT_KEEP(0.5)**, 아니면 1.0. 근거: 2026-07-15 백테스트(4/9~7/10 63거래일) — sev3 이벤트 밤 선정종목 일평균 −0.74% vs 평일 +1.04%(Welch t=−2.27, 혼재일 제외 t=−2.13, 음수일 62% vs 25%). **PPI(sev2)는 +3.6%로 감액 근거 없음 → 관찰 전용**(진단 기록만). 금통위(09:50)는 시가 매도 후라 자연히 창 밖. 적용: 선물 keep 과 곱한 뒤 `effective_keep` 결합 하한(SEED_COMBINED_MIN_MULT) 클램프. **관찰 축**: VIX 레벨(25~35 램프)·WTI 급등(+3~6%p)·원달러 급등(+1~2%p) — 호르무즈류 지정학 쇼크 프록시. keep 을 계산해 진단에만 기록, 감액 미적용. 축끼리 min 결합(같은 쇼크 이중 감액 방지) — 승격 시에도 futures_gate 와 곱이 아닌 min 으로 붙일 것. ⛔ **지금 설계대로 승격 금지**(2026-08-03 백테스트, 4/9~7/31 75거래일): VIX 축은 **부호가 반대**(VIX 높을수록 익일 성적 좋음 — 전체 corr +0.318/t=+2.87, 상위⅓ +1.77% vs 하위⅓ +0.06% → 현행 램프는 담아야 할 때 깎는다. 단 월별 5월 t=−3.13/6월 t=+3.96 로 불안정해 역방향 승격도 근거 없음 → 부호 재검정 전까지 관찰 유지. 표본 기간 VIX≥20 은 3일뿐이라 임계 25 는 미발동). WTI 축은 **기각**(매수시점 가용값 t=−0.44, 보유 밤 실변동조차 t=+0.42 무관계 — 같은 창 NQ 선물 t=+3.69 로 갭 경로는 유가가 아닌 미 기술주 축이고 futures_gate 가 이미 담당. 충격 크기 컷도 N=2/3/4%p 에서 t=−0.65/−1.58/−0.13 비단조 + 7월 부호 반전). 유가를 쓸 곳이 있다면 총 시드 축이 아니라 운송장비/부품 섹터 rule(t=−1.78, 미달) 쪽. 세 축 원값은 재검정 표본으로 계속 진단에 적재. 캘린더 조회 실패 시 미개입(1.0). **매 판단(미개입 포함)을 `audit_log('macro_gate')`에 기록** → 모니터 탭 활동 피드 노출. `/buy-preview` 응답 `macro` 키로 동일 반영. 캘린더 고갈은 jongalab `macro_event_check` 잡(월 08:20)이 감시 |
| 뉴스 베토(악재 강제청산) | `news_veto.py`, `monitor.py` + jongalab `news_guard` | 밤사이 중대 악재 판정(jongalab OpenAI, confidence≥85 게이트) 종목을 monitor 가 **개장 즉시·가격 무관 전량 매도**(tag=newsveto, 가장 이른 거래소 — NXT 가능 08시대 / 불가 종목은 09:00 KRX 개장 후). `execute_sell` 재사용이라 멱등키·paper/live 분기 동일, 매도는 리스크 게이트 미경유(탈출 허용). 판정 조회 실패·비활성 시 미개입 — 하드손절/스탑/09:28 데드라인 백스톱 불변. severe 는 jongalab upsert 에서 1→0 강등 금지. 매 발동을 `audit_log('monitor_newsveto')` 기록 → 모니터 탭 활동 피드 노출 |
| 정합성 점검 | `reconcile.py` | 매일 브로커 잔고 vs 로컬 포지션 대조 |
| 미실행 감시(dead-man's switch) | `watchdog.py` + `audit_log` worker_done 마커 | 핵심 워커가 완료 시 마커를 남기고, watchdog(평일 09:35)가 마커 누락 시 텔레그램 경보. jongalab `job_run` 신선도(2h)로 통합 스케줄러 중단도 함께 감시 |

튜닝 파라미터(`config.py`): `STOP_BUFFER_PCT`(갭다운 버퍼),
`TRAIL_PCT`(트레일링), `HARD_STOP_LOSS_PCT`(하드 손절), `SEED_MAX_NAME_PCT`(종목당 시드 캡,
기본 0.25 — 하한가에선 손절이 물리적으로 불가하므로 단일 종목 최악 손실은 이 캡으로만 봉쇄된다).

---

## 프론트엔드 (`frontend/`, :3001)
홈(당일 손익·매수·보유·매수 프리뷰) · 모니터(워커 하트비트·활성 플랜) · 히스토리(월/일 주문) ·
캘린더(월간 손익) · 설정(킬스위치·리스크 한도·블록리스트·레버리지 ETF 대체매수). 관리자 비밀번호 로그인(httpOnly 쿠키).

**거시 이벤트 표시** (`GET /macro-events?month=YYYYMM` — `macro_gate.month_events`, jongalab `macro_event` 읽기):
- **캘린더 탭**: 날짜 셀 우상단 점 마커(주황=sev3 FOMC·CPI·고용 → 전야 시드 축소 대상 / 회색=sev2 PPI·금통위 관찰)
  + 하단 범례. 날짜를 누르면 상세에 이벤트 뱃지(이름·발표시각 KST). 발표일 기준 표시 — sev3 감액은 그 전날 밤 매수분에 걸린다.
- **홈 '오늘 매수 예정' 카드**: `/buy-preview` 의 `macro` 진단으로 오늘 밤 이벤트를 안내 —
  sev3 있으면 "오늘 밤 {이벤트} — 시드 ×keep 축소"(주황), sev2 만 있으면 "발표 예정 — 감액 없음(관찰)"(회색).
  레짐 게이트 축소(×multiplier)도 같은 자리에 안내. 조회 실패 시 이벤트 표시만 생략(달력·프리뷰는 정상 동작).

**반복 거부/취소 표시 병합**: 히스토리 탭은 같은 날 (종목·방향·상태)가 같은 rejected/canceled 행을
한 줄로 묶어 "거부 ×238 · 08:17~09:30"(횟수·시간범위)로 보여준다(`collapseRepeats`, 표시 전용 —
API/DB·재시도 동작 무변경). 하한가 매도 거부(HLB 238건)·IOC 소멸 취소(한화오션 55건)가 15초 폴링마다
수백 행 쌓이던 표시 스팸 대응. 15초 재시도 자체는 하한가 풀림 포착을 위해 의도적으로 유지한다.

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
롤링 엣지 게이트 배수 매핑·역전 판정(`regime_gate`), 선물 섹터 게이트 클래스 매핑·섹터별 keep 차등·미개입 분기(`futures_gate`),
거시 이벤트 게이트 보유 창·severity 매핑·프록시 관찰 전용·미개입 분기(`macro_gate`),
뉴스 베토 전량매도·0순위 우선·fail-safe(빈 판정/조회 실패에도 하드손절 정상)·venue 보류·TTL 캐시(`test_news_veto`),
레버리지 ETF 치환 순수 로직(무매핑 무치환·코드/이름만 교체·원신호 id 유지·ETF 코드 결측 방어, `test_leverage_swap`),
시초가 단계 분기(`test_settle`): 단계별 대상 종목, **갭상승=전량매도·plan 미생성**(1주 포함), 갭하락=절반매도+시초가−버퍼 plan,
실시간 피드 폴백·틱 판정(`test_realtime_feed`): TTL 초과/미구독/다른 보드/피드 예외 → REST 폴백, 부호 붙은 현재가 절대값
파싱, 체결통보 1회 소비, 등록 상한 캡, 틱 경로는 하드손절 즉시 집행하되 **트레일링 상향은 안 함**(15초 경로만 함),
매도 거부 시 쿨다운이 재전송 억제·경과 후 재시도 허용, 체결 확인 시 스냅샷에서 제거.
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
