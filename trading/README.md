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
│   ├── seed_allocator.py       # 점수 가중 시드 배분(거래소별)
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
└── sql/                        # trading DB 스키마
```

---

## 집행 흐름 (신호 → 체결 → 청산 → 정합성)

종가베팅 1사이클을 거래소(KRX/NXT)별로 집행한다.

```
[jongalab closing_bet] → trade_signal(pending)
        │
signal_executor (KRX 15:00 / NXT 19:30)
  · 블록리스트 제외 → 거래소 분류 → seed_allocator 배분
  · 15초 폴링으로 장중 고점 추적, 고점 대비 되돌림(BUY_PULLBACK_PCT) 시 매수(IOC)
  · 마감 시각에 잔여분 시장가 집행 → 신호 status 갱신(done/skipped/rejected)
        │
fills_sync (15:31 / 19:55) · ka10076 체결 동기화 → position 갱신 + 매수 텔레그램 알림
        │
settle --venue nxt (08:05)
  · NXT 시초가로 갭 판정 → 절반 매도(tag=nxt) → settle_plan 생성(stop_price 설정)
monitor (08:01~09:30, 15초 폴링)
  · 하드 손절(HARD_STOP_LOSS_PCT) · 트레일링 스톱(TRAIL_PCT, 단조 상승) → 돌파 시 전량 매도(tag=stop)
  · 스테일 주문 취소 + dead 주문 정리 + 체결 동기화 + 하트비트 로그(대시보드 표시)
settle --venue krx (09:28) · 잔여 보유분 전량 청산(마감 데드라인) → 오버나잇 방지
        │
reconcile (20:00) · kt00018 잔고 vs 로컬 position 대조 → 드리프트 알림
```

> **첫 구현 범위는 종가베팅 집행만**이다. 장중 상시 손절 감시(`position_monitor`)·멀티 전략은 다음 단계.

---

## 안전장치 (구현됨)
| 장치 | 위치 | 내용 |
|---|---|---|
| 모드 | `config.py`, `execution_engine.py` | `TRADING_MODE=paper`(기본, 미전송·즉시 시뮬레이션) / `live`(실주문) |
| 글로벌 킬스위치 | env `TRADING_KILL_SWITCH=1` + DB `kill_switch` | 둘을 OR — 하나라도 켜지면 전체 차단 |
| 서킷브레이커 | `risk_engine.py` + `risk_state.py` | 일일 실현손실 ≤ -MAX_DAILY_LOSS 시 자동 킬스위치 발동 |
| 하드 한도 | `risk_engine.py` | 일일 주문수·종목당 명목금액·동시 보유종목수 상한 |
| 멱등키 | `execution_engine.py`, `order.py` | `YYYYMMDD:signal_id:side` UNIQUE — cron 재실행 중복 방지(거부 `:x`, dead `:dead` 접미사로 키 해제) |
| 하드 손절 / 트레일링 | `monitor.py`, `settle_plan.py` | HARD_STOP_LOSS_PCT 즉시 전량 / TRAIL_PCT 단조 상승 스톱 |
| 불변 감사로그 | `audit_log.py` | append-only(UPDATE/DELETE 없음) |
| 블록리스트 | `blocklist.py`, `signal_executor.py` | 수동 보유 종목 자동매수 차단 |
| 정합성 점검 | `reconcile.py` | 매일 브로커 잔고 vs 로컬 포지션 대조 |

튜닝 파라미터(`config.py`): `BUY_PULLBACK_PCT`(되돌림 매수), `STOP_BUFFER_PCT`(갭다운 버퍼),
`TRAIL_PCT`(트레일링), `HARD_STOP_LOSS_PCT`(하드 손절).

---

## 프론트엔드 (`frontend/`, :3001)
홈(당일 손익·매수·보유·매수 프리뷰) · 모니터(워커 하트비트·활성 플랜) · 히스토리(월/일 주문) ·
캘린더(월간 손익) · 설정(킬스위치·리스크 한도·블록리스트). 관리자 비밀번호 로그인(httpOnly 쿠키).

## 기동
```bash
uv run --directory trading uvicorn api:app --host 127.0.0.1 --port 8002   # API
cd trading/frontend && npm run dev                                        # 대시보드(:3001)
```

## 유지보수
1. 5가지 사전 검토(필요성·기존 코드·최단 구조·최소 혼란 흐름·유지보수성) 후 착수.
2. 변경 전 이 README 로 흐름·안전장치를 파악하고, 변경 후 해당 섹션을 갱신한다.
3. `risk_engine.py`·`execution_engine.py` 는 사용자 확인 없이 수정 금지.
4. 검증: `uv run --directory trading python -m py_compile <file>`, `paper` 모드로 동작 확인 후 보고.
