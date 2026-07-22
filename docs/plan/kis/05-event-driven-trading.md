# Phase 5 — 자동매매를 polling에서 이벤트 중심으로 전환

## 1. 목표

Phase 4의 시세·주문·체결 이벤트를 기존 자동매매 상태 머신에 연결한다. 정상 운영의 주경로는 이벤트로
바꾸되 시작, 재연결, timeout, 장마감의 REST 조회는 복구 경로로 남긴다.

Polling 제거 대상과 유지 대상을 구분한다.

| 대상 | 현재 | 변경 후 |
|---|---|---|
| 보유종목 현재가 | `monitor.py` 15초 polling | quote event 즉시 평가 |
| 주문·체결 반영 | `fill_sync.py`/`order_maintenance.py` 반복 조회 | WS inbox projector |
| 시작·재연결 누락 | polling 결과에 의존 | REST bootstrap/catch-up |
| 주문 deadline | timer/heartbeat | 유지, timeout 시 REST 확인 |
| watchdog | 주기 실행 | 유지 |
| 장마감 reconcile | REST | 유지 |
| 대시보드 refresh | HTTP polling | 이번 범위에서 유지 |

## 2. 책임 분리

현재 worker loop 안의 업무 로직을 재사용 가능한 서비스로 추출한다.

```text
trading/core/
├── position_monitor.py       # on_quote, stop/trailing 판단
├── broker_event_projector.py # inbox → order/fill/position/audit
├── broker_reconciler.py      # REST snapshot/catch-up
└── stream_guard.py           # 신규매수 허용 여부

trading/workers/
├── kis_stream.py             # 이벤트 주경로
├── monitor.py                # 키움 polling runner 보존
├── fill_sync.py              # catch_up_fills 명령/안전망으로 축소
└── order_maintenance.py      # deadline·housekeeping 중심으로 축소
```

`monitor.py`를 삭제하지 않는다. 공통 `PositionMonitor`를 호출하는 키움용 polling runner로 남겨
`BROKER_PROVIDER=kiwoom` rollback이 가능하게 한다.

## 3. 시세 이벤트 처리 흐름

```text
KIS quote event
  │ validate venue/time/price
  ▼
PositionMonitor.on_quote(event)
  │ load active position state/cache
  ├── peak price update
  ├── stop-loss / stop-profit / trailing-stop 판단
  ├── duplicate decision guard
  └── sell intent 생성
          │
          ▼
ExecutionEngine + BrokerClient(KIS REST)
          │
          ▼
order row → WS order/fill event → projector
```

시세 tick마다 DB에서 모든 position을 다시 읽지 않는다. 시작과 position 변경 시 cache를 갱신하고,
peak/최근가는 write throttle과 의미 있는 변화 조건을 적용한다. 매도 의사결정은 로컬 lock과 order 상태로
동일 종목 중복 주문을 막는다.

## 4. venue와 가격 선택

`PositionMonitor`가 받을 quote는 주문/전략 시간대에 맞는 effective price여야 한다.

- event에는 `exchange`, `event_at`, `received_at`, `price`를 반드시 포함한다.
- KRX와 NXT 이벤트를 한 timestamp stream으로 섞지 않고 venue별 최신값을 유지한다.
- 현재 시간대별 가격 선택 규칙을 한 함수로 이동한다.
- 통합 시세가 기존 의미를 대체한다고 검증되기 전에는 KRX/NXT 명시 규칙을 유지한다.
- 장외/과거 이벤트, 현재 시각보다 비정상적으로 미래인 이벤트, 0/음수 가격은 의사결정에서 제외한다.

## 5. 손절·스탑·트레일링의 동등성

기존 `monitor.py`의 계산식과 상태 전이는 바꾸지 않고 입력 주기만 이벤트로 바꾼다.

1. 현재 polling loop의 순수 판단 부분을 `PositionMonitor.evaluate(position, quote)`로 추출한다.
2. 동일한 price sequence fixture를 polling runner와 event runner에 넣는다.
3. 매도 조건, 이유, 수량, 주문유형이 동일한지 golden test로 고정한다.
4. event가 더 촘촘해져 peak price가 달라질 수 있는 효과는 별도 관측 지표로 기록한다.
5. 전략 임계치 변경은 이번 Phase에 포함하지 않는다.

## 6. 주문·체결 projector

`BrokerEventProjector`는 inbox 한 건을 transaction 안에서 반영한다.

```text
pending inbox row claim
   │
   ├── order status transition
   ├── fill insert (unique broker event key)
   ├── position qty/avg price/pnl update
   ├── audit_log append
   └── inbox processed
```

규칙:

- order 상태는 `submitted → accepted → partial → filled/cancelled/rejected`의 허용 전이만 사용한다.
- 늦은 이벤트가 terminal 상태를 되돌리지 못한다.
- fill insert와 position 갱신은 같은 transaction이다.
- unique 충돌은 이미 처리된 이벤트로 보고 성공 종료한다.
- 미지의 order event는 버리지 않고 `unmatched` 상태와 alert를 남긴 뒤 REST 대조한다.
- projector 실패는 수신 socket을 끊지 않고 retry backlog로 남긴다.

## 7. REST bootstrap/catch-up/reconcile

### 시작 시

1. 로컬 open position/order/fill cursor 읽기.
2. KIS balance, open orders, 당일 executions 전체 pagination 조회.
3. broker에만 있는 주문/체결을 inbox 형식으로 합성해 projector에 투입.
4. 로컬에만 있는 열린 상태를 `reconciliation_issue`로 기록.
5. 차이가 해결된 뒤 stream healthy.

### 재연결 시

disconnect 시작 시각보다 안전 여유를 둔 범위로 executions를 다시 조회한다. dedup key가 있으므로 이미 받은
체결도 함께 조회해도 된다. open order와 balance까지 대조한 뒤 healthy로 복귀한다.

### 장마감 시

전체 당일 executions, open orders, balance, 로컬 fill/position을 대조한다. 미해결 차이가 있으면 다음 거래일
신규 매수를 차단하고 운영 알림을 보낸다.

## 8. signal executor와 deadline

`signal_executor.py`의 대기/heartbeat는 가격 polling과 다른 책임이므로 유지한다.

- 주문 전송 뒤 WS 접수/체결 이벤트를 기다린다.
- deadline 안에 이벤트가 없으면 REST open orders/executions를 조회한다.
- REST에서도 접수 여부가 불명확하면 `ambiguous`로 두고 같은 신호를 재주문하지 않는다.
- 부분체결이면 체결 수량을 우선 반영하고 잔량 처리 정책을 기존과 동일하게 적용한다.
- stream unhealthy이면 신규 매수 신호를 실행하지 않는다.

## 9. order maintenance 변경

주기 polling을 전부 없애지 않고 역할을 housekeeping으로 제한한다.

- 주문 deadline 도달 검사.
- 오래된 pending inbox 및 unmatched event 검사.
- stream health와 마지막 reconcile 확인.
- 제한된 빈도의 REST open-order audit.
- 취소/정정이 필요한 주문만 KIS REST 호출.

각 cycle마다 모든 체결을 조회하는 정상 경로는 제거하고, catch-up 명령과 장애 안전망으로 남긴다.

## 10. stream guard

신규 매수 허용 조건을 중앙화한다.

```text
allow_new_buy =
    broker_provider == kis
    AND stream.connected
    AND stream.healthy
    AND quote freshness within threshold
    AND reconcile freshness within threshold
    AND inbox backlog below threshold
    AND no unresolved reconciliation issue
```

stream이 unhealthy인 경우:

- 신규 매수: 차단.
- 미체결 신규 매수: 필요 시 취소.
- 손절/청산 매도: REST snapshot으로 가격·잔량 확인 후 허용.
- 중복/불명확 주문: 추가 주문 금지, reconcile 우선.

“WS 장애 시 키움으로 매도” 같은 broker 교차 fallback은 금지한다. KIS 포지션은 KIS로만 축소한다.

## 11. settle과 평가가격

`settle.py`는 다음 우선순위로 평가가격을 얻는다.

1. venue·시각이 유효한 `broker_quote_snapshot`.
2. KIS REST 현재가 snapshot.
3. 둘 다 실패하면 마지막 가격으로 확정 처리하지 않고 stale 상태 기록.

실현손익은 로컬 fill 기반 계산과 KIS REST 손익 조회를 모두 저장해 차이를 관제한다. 공급자별 수수료·세금
필드가 다르므로 정규화 DTO에서 구분한다.

## 12. 기존 워커의 보존 모드

| 워커 | KIS 기본화 후 | 키움 rollback 시 |
|---|---|---|
| `monitor.py` | 상시 중지 또는 reconcile-only | 기존 interval로 공통 monitor 호출 |
| `fill_sync.py` | 시작/재연결/수동 catch-up | 기존 polling mode |
| `order_maintenance.py` | deadline·audit | 기존 미체결 polling mode |
| `reconciliation.py` | KIS REST 정본 대조 | 키움 REST 정본 대조 |
| `kis_stream.py` | 상시 실행 | trading dispatch 중지, 연결은 shadow 가능 |

한 worker 안에서 provider를 매 iteration 바꾸지 않고 시작 시 mode를 고정한다.

## 13. 구현 순서

1. 기존 monitor 판단 로직을 공통 서비스로 추출하고 golden test 작성.
2. 키움 polling runner가 새 서비스를 호출하도록 연결해 회귀 확인.
3. quote event를 `PositionMonitor.on_quote()`에 연결.
4. broker event projector와 상태 전이 테스트 구현.
5. `fill_sync` 로직을 재사용해 REST catch-up service 작성.
6. startup/reconnect/장마감 reconcile 연결.
7. signal deadline과 order maintenance를 이벤트 우선으로 변경.
8. stream guard와 reduce-only fallback 적용.
9. settle의 snapshot→REST fallback 연결.
10. 모의투자 전체 cycle 검증 후 polling normal path 비활성화.

## 14. 검증 시나리오

- 같은 price sequence에서 기존 polling과 새 event monitor의 매도 판단 일치.
- 빠른 가격 급락에서 한 번만 손절 주문 생성.
- 부분체결 2건과 전량체결 이벤트가 fill/position에 정확히 반영.
- 체결→접수 역순 이벤트에서 filled 상태 유지.
- projector 중간 실패 후 retry해 중복 fill이 생기지 않음.
- disconnect 중 체결을 재연결 REST catch-up으로 복구.
- WS 이벤트 미도착 시 deadline REST 조회로 접수 상태 확인.
- stream stale에서 신규 매수 차단, KIS reduce-only 매도 허용.
- 장마감 대조에서 broker/local 차이가 이슈로 남고 다음 신규매수를 차단.
- `BROKER_PROVIDER=kiwoom`에서 polling rollback 정상 동작.

## 15. 완료 기준 (DoD)

- [ ] 가격 감시의 정상 경로가 quote event다.
- [ ] 주문·체결 반영의 정상 경로가 durable inbox projector다.
- [ ] 기존 손절·스탑·트레일링 계산식과 주문 의도가 바뀌지 않았다.
- [ ] 시작·재연결·장마감 REST reconcile이 자동 실행된다.
- [ ] timeout·누락·중복·역순·부분체결 시나리오가 테스트됐다.
- [ ] stream unhealthy 신규매수 차단과 reduce-only 규칙이 적용된다.
- [ ] 기존 키움 polling 워커와 client가 rollback 가능한 상태로 남아 있다.
- [ ] 민감 파일 변경은 사용자 승인 범위 안에서 수행됐다.

## 16. 위험과 대응

| 위험 | 대응 |
|---|---|
| tick 증가로 중복 매도 | 종목 lock + 열린 매도 주문 확인 + decision idempotency |
| 이벤트 순서가 상태를 되돌림 | 허용 상태 전이와 terminal 보호 |
| WS 누락으로 position 불일치 | 시작/재연결/장마감 REST reconcile |
| DB 부하 | memory cache, snapshot throttle, event별 최소 transaction |
| polling 제거로 deadline 유실 | timer/maintenance/watchdog는 유지 |
| 장애 시 다른 broker로 잘못 주문 | broker 교차 fallback 금지, KIS reduce-only만 허용 |
