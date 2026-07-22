# Phase 4 — KIS WebSocket 단일 runtime

## 1. 목표

KIS WebSocket 연결, 구독, 암호화 주문·체결통보, 재연결과 상태 관제를 한 프로세스가 소유하도록 만든다.
이 단계에서는 이벤트를 안전하게 수신·저장하는 데 집중하고, 실제 자동매매 의사결정 전환은 Phase 5에서 한다.

## 2. 왜 단일 runtime인가

워커마다 WebSocket을 열면 구독 한도, approval key, 재연결, 중복 이벤트와 관제가 분산된다. 따라서
`trading-kis-stream` 한 프로세스가 외부 연결을 독점하고 내부 DB/event handler로 전달한다.

```text
KIS WebSocket
  ├── H0STCNT0  KRX 실시간 체결가
  ├── H0NXCNT0  NXT 실시간 체결가
  ├── H0UNCNT0  통합 체결가 (검증 후 선택)
  ├── H0STCNI0  실전 주문·체결통보
  └── H0STCNI9  모의 주문·체결통보
          │
          ▼
trading-kis-stream
  ├── connection/session manager
  ├── subscription registry
  ├── parser + AES decryptor
  ├── durable event inbox
  ├── quote snapshot writer
  └── stream health/reconcile trigger
```

실제 TR ID와 필드 순서는 공식 예제 fixture로 고정하고 구현 시작 시 다시 확인한다.

## 3. 구현 파일

```text
trading/core/
├── kis_ws.py                         # 연결, approval, subscribe, PINGPONG
├── kis_ws_schema.py                  # TR별 field order와 typed event
├── kis_ws_crypto.py                  # AES key/IV 메모리 보관과 복호화
└── repository/
    ├── broker_event.py               # durable inbox·claim·processed
    ├── quote_snapshot.py             # 종목별 최신가
    └── stream_state.py               # 연결/지연/구독 상태
trading/workers/
└── kis_stream.py                     # lifecycle과 event dispatch
trading/tests/
├── fixtures/kis_ws/
└── test_kis_ws_*.py
trading/sql/
└── 5. migrate_broker_stream.sql
```

기존 `jongalab/workers/kis_night_futures_ws.py`의 PINGPONG, timeout, 재연결, 종료시각, write throttle
패턴을 재사용한다. 국내주식 체결통보에는 AES 복호화와 주문상태 projector가 추가된다.

## 4. DB 설계

### 4.1 durable inbox

```sql
CREATE TABLE broker_event_inbox (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    broker          VARCHAR(10) NOT NULL,
    environment     VARCHAR(10) NOT NULL,
    event_key       VARCHAR(160) NOT NULL,
    event_type      VARCHAR(30) NOT NULL,
    tr_id           VARCHAR(20) NOT NULL,
    stk_cd          VARCHAR(20) NULL,
    order_no        VARCHAR(40) NULL,
    event_at        DATETIME(6) NULL,
    received_at     DATETIME(6) NOT NULL,
    payload         JSON NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INT NOT NULL DEFAULT 0,
    processed_at    DATETIME(6) NULL,
    last_error      TEXT NULL,
    UNIQUE KEY uq_broker_event (broker, environment, event_key),
    INDEX idx_event_pending (status, received_at),
    INDEX idx_event_order (broker, order_no, event_at)
);
```

원본 암호문, AES key/IV, access token은 저장하지 않는다. `payload`에는 복호화·정규화된 업무 필드와
필요한 원본 코드만 저장하며 계좌 식별자는 마스킹한다.

### 4.2 최신 시세 snapshot

```sql
CREATE TABLE broker_quote_snapshot (
    broker          VARCHAR(10) NOT NULL,
    exchange        VARCHAR(8) NOT NULL,
    stk_cd          VARCHAR(20) NOT NULL,
    price           DECIMAL(18,4) NOT NULL,
    volume          BIGINT NULL,
    event_at        DATETIME(6) NOT NULL,
    received_at     DATETIME(6) NOT NULL,
    sequence_key    VARCHAR(100) NULL,
    PRIMARY KEY (broker, exchange, stk_cd),
    INDEX idx_quote_received (received_at)
);
```

모든 tick을 적재하는 테이블이 아니다. 종목·venue별 최신 상태만 upsert하고 DB write를 throttle한다.
손절 계산은 process memory의 최신 이벤트를 우선 사용하고, 다른 프로세스와 복구 시 snapshot을 사용한다.

### 4.3 stream 상태

```sql
CREATE TABLE broker_stream_state (
    stream_name         VARCHAR(40) PRIMARY KEY,
    broker              VARCHAR(10) NOT NULL,
    environment         VARCHAR(10) NOT NULL,
    connected           TINYINT(1) NOT NULL DEFAULT 0,
    healthy             TINYINT(1) NOT NULL DEFAULT 0,
    connected_at        DATETIME(6) NULL,
    last_message_at     DATETIME(6) NULL,
    last_quote_at       DATETIME(6) NULL,
    last_order_event_at DATETIME(6) NULL,
    last_reconcile_at   DATETIME(6) NULL,
    reconnect_count     INT NOT NULL DEFAULT 0,
    subscription_count  INT NOT NULL DEFAULT 0,
    last_error          TEXT NULL,
    updated_at          DATETIME(6) NOT NULL
);
```

## 5. 연결 lifecycle

```text
STARTING
  │ token + approval key
  ▼
CONNECTING ──fail──► BACKOFF
  │ connected
  ▼
SUBSCRIBING
  │ desired == acknowledged
  ▼
RECONCILING ── REST balance/open orders/executions catch-up
  │ success
  ▼
HEALTHY
  │ stale / close / parse burst / auth error
  ▼
DEGRADED → disconnect → BACKOFF → CONNECTING
```

`connected=true`만으로 `healthy=true`가 되지 않는다. 필수 구독 확인과 REST catch-up이 끝나야 신규 매수에
사용 가능한 상태가 된다.

재연결 backoff에는 jitter와 상한을 둔다. 인증 오류는 무한 빠른 재시도하지 않고 토큰/approval을 한 번
갱신한 뒤 실패 상태를 노출한다.

## 6. 구독 registry

desired subscription은 DB 상태에서 계산한다.

- 열린 position 종목.
- pending/partial order 종목.
- 당일 실행 대기 중인 실제 매수 후보.
- 필수 주문·체결통보 HTS ID.

전 종목 universe, shadow 분석 종목 전체, 대시보드 조회 종목은 trading stream에 넣지 않는다.

registry는 `desired`, `sent`, `acknowledged` 세 집합을 관리한다. position/order 변화가 오면 diff만
subscribe/unsubscribe하고, 재연결 시 acknowledged를 비운 뒤 전체 desired를 재등록한다.

공식 안내의 세션 등록 한도보다 낮은 내부 상한을 둔다. 상한 초과 시 우선순위는 열린 position → 미체결
order → 매수 후보 순이며, 열린 position을 탈락시키지 않는다.

## 7. 메시지 처리

### 7.1 제어 메시지

- JSON PINGPONG은 지연 없이 echo/reply한다.
- subscribe ack의 성공/실패를 registry에 반영한다.
- key/IV를 포함한 체결통보 등록 응답은 메모리에만 두고 로그를 마스킹한다.
- 알 수 없는 TR ID는 raw 전체를 로그하지 않고 길이·TR ID·해시만 남긴다.

### 7.2 시세 이벤트

1. TR별 고정 field order로 parse.
2. 종목코드, venue, 체결가, 체결시각, 거래량을 typed event로 변환.
3. 가격·시각 유효성 검사와 이전 event보다 오래된 값 차단.
4. process memory 갱신.
5. 설정된 throttle 간격으로 `broker_quote_snapshot` upsert.
6. Phase 5의 monitor handler에 dispatch.

### 7.3 주문·체결통보

1. AES key/IV로 payload 복호화.
2. 접수, 거부, 정정, 취소, 부분체결, 전량체결을 정규화.
3. 안정적인 `event_key` 생성.
4. `broker_event_inbox`에 insert; unique 충돌은 정상 중복으로 처리.
5. commit 뒤 projector를 깨운다.
6. projector 실패는 inbox `pending/retry`로 남기고 수신 loop를 막지 않는다.

## 8. event key와 순서

KIS가 유일 체결번호를 제공하면 `broker + environment + TR + 체결번호`를 우선 사용한다. 접수/거부처럼
체결번호가 없는 이벤트는 주문번호, 상태코드, 통보시각, 수량 등 공식 필드 조합을 versioned canonical
string으로 만들고 hash한다.

- 수신 순서를 업무 순서로 가정하지 않는다.
- 같은 주문의 늦은 접수 이벤트가 이미 전량체결 상태를 되돌리지 못하게 status transition을 단조롭게 만든다.
- 이벤트 시각이 같아도 서로 다른 부분체결을 합치지 않는다.
- dedup key 규칙을 바꿀 때 version prefix를 올린다.

## 9. stale와 health 기준

장 상태를 고려해 stale threshold를 다르게 적용한다.

- 연결 자체의 `last_message_at`.
- 실제 구독 종목이 있을 때의 `last_quote_at`.
- 주문이 pending일 때의 주문통보 상태.
- desired 대비 acknowledged 구독 수.
- inbox pending oldest age와 처리 실패 횟수.
- 마지막 REST reconcile 성공 시각.

거래가 없는 종목의 quote 부재만으로 연결을 실패 처리하지 않는다. WebSocket PINGPONG과 시장 전체 heartbeat,
구독 ack, REST 대조를 함께 본다.

## 10. 장애·복구 규칙

| 상황 | runtime 동작 | trading 영향 |
|---|---|---|
| 순간 disconnect | unhealthy 표시, 재연결 backoff | 신규 매수 차단 후보 |
| 재연결 성공 | 전체 재구독 후 REST catch-up | reconcile 완료 전 unhealthy |
| 체결 parser 실패 | inbox/샘플 안전 저장, alert | 해당 주문 REST 조회 |
| inbox projector 실패 | retry 상태, 수신 지속 | 오래된 pending 경보 |
| 구독 상한 도달 | 우선순위 적용, 후보 구독 거절 | 열린 position 보호 |
| quote stale | REST snapshot fallback 요청 | 신규 매수 차단, reduce-only 허용 |
| key/IV 오류 | 세션 재등록 한 번 | 반복 시 stream degraded |

## 11. PM2 등록

`ecosystem.config.js`에 `trading-kis-stream` 상시 앱 하나만 추가한다.

- 자동 재시작은 허용하되 프로세스 내 backoff와 충돌하지 않게 설정한다.
- 동일 environment에서 중복 instance가 실행되지 않도록 instances=1을 고정한다.
- SIGTERM 시 신규 dispatch를 멈추고 pending DB commit을 마친 뒤 unsubscribe/close한다.
- 시작 시 DB lock으로 active owner를 확인해 실수로 두 프로세스가 떠도 하나만 연결한다.

## 12. 구현 순서

1. 공식 메시지 fixture 수집·비밀 제거·필드 순서 고정.
2. parser, crypto, normalized event 단위 테스트.
3. inbox/snapshot/state migration과 repository.
4. 연결/PINGPONG/ack/reconnect 상태머신.
5. 동적 subscription registry와 내부 상한.
6. quote snapshot dispatch.
7. 주문·체결통보 inbox 저장과 dummy projector.
8. startup/reconnect REST catch-up hook.
9. PM2·health·관제 로그 추가.

## 13. 검증

- 공식 fixture의 KRX/NXT/통합 시세 parse.
- 실전/모의 체결통보 복호화와 필드 parse.
- 같은 메시지를 여러 번 넣어 inbox가 한 건인지 확인.
- 부분체결 여러 건이 각각 고유 event인지 확인.
- PINGPONG, 정상 close, 강제 socket 종료, 네트워크 단절, 인증 만료 재연결.
- 재연결 뒤 desired 전체 재구독과 REST catch-up 완료 전 healthy가 되지 않는지 확인.
- 구독 상한에서 열린 position이 유지되는지 확인.
- AES key/IV·토큰·계좌번호가 로그와 DB에 남지 않는지 확인.
- SIGTERM 후 재시작해 pending inbox가 유실 없이 처리되는지 확인.

## 14. 완료 기준 (DoD)

- [ ] 외부 KIS WS 연결은 `trading-kis-stream` 한 프로세스만 소유한다.
- [ ] 시세와 주문·체결통보 parser가 fixture 테스트를 통과한다.
- [ ] 주문 이벤트는 업무 반영 전에 durable inbox에 commit된다.
- [ ] 중복·역순·부분체결을 안전하게 처리할 event key와 상태 전이가 있다.
- [ ] 재연결 뒤 재구독+REST catch-up 전에는 healthy가 아니다.
- [ ] 구독 수, 마지막 이벤트, reconnect, inbox backlog가 관제 가능하다.
- [ ] 키움 polling 워커는 아직 삭제되지 않고 그대로 실행 가능하다.

## 15. 위험과 대응

| 위험 | 대응 |
|---|---|
| WS 이벤트 유실 | 시작/재연결/장마감 REST catch-up |
| 중복 또는 역순 수신 | durable unique key + 단조 상태 전이 |
| DB write 폭증 | latest snapshot upsert throttle, 전 tick 저장 금지 |
| 구독 한도 초과 | 동적 최소 구독, 내부 상한, position 우선순위 |
| 복호화 비밀 유출 | 메모리 전용, 구조화 로그 필터, fixture 비식별화 |
| 다중 runtime 중복 처리 | PM2 instances=1 + DB owner lock |
