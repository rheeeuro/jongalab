# Phase 3 — KIS 주문·계좌 REST adapter

## 1. 목표

`trading`의 키움 주문/계좌 client 앞에 broker-neutral 계약을 만들고 KIS REST 구현을 추가한다.
주문 전송은 계속 REST이며, WebSocket은 Phase 4부터 주문·체결 상태의 빠른 통지 경로로 사용한다.

이 단계에서는 기본 broker를 키움으로 유지한다. KIS 경로는 fixture, 모의투자, 조회-only smoke test로 검증한다.

## 2. 현재 기능과 KIS 구현 범위

| 현재 키움 기능 | KIS 구현 | 용도 |
|---|---|---|
| `kt10000` 매수 | 국내주식 현금주문 buy | 신규/추가 매수 |
| `kt10001` 매도 | 국내주식 현금주문 sell | 청산·손절 |
| `kt10002` 정정 | 국내주식 정정취소 revise | 가격/수량 정정 |
| `kt10003` 취소 | 국내주식 정정취소 cancel | 미체결 취소 |
| `kt00018` 잔고 | 주식잔고조회 | position reconcile |
| `kt00001` 예수금 | 매수가능/예수금 계열 조회 | 시드·가용현금 |
| `ka10074` 실현손익 | 기간별/일별 손익 조회 | settle·대조 |
| `ka10075` 미체결 | 주문체결/미체결 조회 | bootstrap·maintenance |
| `ka10076` 체결 | 일별주문체결조회 | catch-up·reconcile |

실제 TR ID, 실전/모의 구분, NXT/SOR 파라미터는 구현 시 공식 샘플을 기준으로
[07-api-coverage.md](07-api-coverage.md)에 확정한다.

## 3. broker-neutral 계약

```text
trading/core/
├── broker_client.py          # Protocol, DTO, factory
├── kiwoom_broker_client.py   # 기존 client를 감싸는 adapter
└── kis_broker_client.py      # KIS REST 구현
```

주요 Protocol은 현재 `execution_engine`, `fill_sync`, `order_maintenance`, `reconciliation`, `settle`이
필요로 하는 기능만 포함한다.

```python
class BrokerClient(Protocol):
    def place_order(self, request: PlaceOrderRequest) -> BrokerOrderResult: ...
    def revise_order(self, request: ReviseOrderRequest) -> BrokerOrderResult: ...
    def cancel_order(self, request: CancelOrderRequest) -> BrokerOrderResult: ...
    def get_balance(self) -> list[BrokerPosition]: ...
    def get_cash(self) -> BrokerCash: ...
    def get_open_orders(self, cursor=None) -> BrokerPage[BrokerOrder]: ...
    def get_executions(self, query) -> BrokerPage[BrokerExecution]: ...
    def get_realized_pnl(self, query) -> BrokerRealizedPnl: ...
```

전략/엔진에는 KIS의 `rt_cd`, `msg_cd`, `ODNO`나 키움 TR 필드가 노출되지 않는다.

## 4. 정규화 DTO

최소 DTO는 다음 정보를 보존한다.

```text
PlaceOrderRequest
  client_order_key, side, stk_cd, qty, price, order_type, venue

BrokerOrderResult
  accepted, broker, order_no, order_org_no, stk_cd,
  requested_qty, message_code, message, raw

BrokerOrder
  broker, order_no, order_org_no, stk_cd, side, venue,
  ordered_qty, filled_qty, remaining_qty, order_price, status, ordered_at

BrokerExecution
  broker, event_key, order_no, execution_no, stk_cd, side,
  qty, price, executed_at, fee, tax
```

`message_code`와 `raw`는 감사/장애 분석용이고 엔진 분기는 `accepted`, 정규화된 `status`와 typed exception을
사용한다. 원본에는 민감 필드를 제거한다.

## 5. 주문 유형과 venue 매핑

중앙 매핑 테이블을 코드와 테스트 fixture로 관리한다.

| 내부 의미 | KIS 매핑 확인 | 안전 규칙 |
|---|---|---|
| KRX 지정가 | 현금주문 `ORD_DVSN` | 모의·소액 검증 후 허용 |
| KRX 시장가 | 현금주문 시장가 코드 | 가격 0/빈 값 계약 확인 |
| NXT 지정가 | NXT/SOR 지원 주문 코드 | NXT 가능종목 확인 |
| NXT 최유리 IOC | 대응 주문구분 코드 확인 필수 | 확인 전 실주문 차단 |
| 정정 | 원주문번호+주문조직번호 | 미체결 수량을 먼저 조회 |
| 취소 | 원주문번호+주문조직번호 | 이미 체결된 수량은 취소 대상 제외 |

문자열을 워커마다 직접 조립하지 않고 `OrderType`, `Venue` enum과 한 개의 mapper로 제한한다.
지원하지 않는 조합은 KIS 요청 전에 `UnsupportedOrderType`으로 실패한다.

## 6. 주문 전송 안전 규칙

1. `client_order_key`로 로컬 중복을 먼저 차단한다.
2. broker factory는 프로세스 시작 시 한 provider만 만든다.
3. KIS 주문 timeout은 자동 재전송하지 않는다.
4. timeout/연결 종료로 접수 여부가 불명확하면 주문조회에서 주문번호·종목·수량·시각을 대조한다.
5. 주문 성공은 HTTP 200이 아니라 `rt_cd`, 주문번호, 응답 계약으로 판정한다.
6. 주문번호와 주문조직번호를 함께 저장한다.
7. 부분체결 뒤 취소는 잔량 기준으로 요청하고, 응답 후 REST/WS로 상태를 재확인한다.
8. paper/live의 TR ID와 base URL을 혼합하지 않는다.
9. `BROKER_PROVIDER=kis`인데 KIS가 실패했다고 키움으로 같은 주문을 자동 전송하지 않는다.

## 7. 스키마 변경

`trading/sql/4. migrate_broker_provider.sql`과 정본 schema에 broker 식별자를 추가한다.

```sql
ALTER TABLE `order`
    ADD COLUMN broker VARCHAR(10) NOT NULL DEFAULT 'kiwoom',
    ADD COLUMN broker_order_no VARCHAR(40) NULL,
    ADD COLUMN broker_order_org_no VARCHAR(20) NULL,
    ADD COLUMN exchange VARCHAR(8) NULL,
    ADD COLUMN last_broker_event_at DATETIME(6) NULL,
    ADD INDEX idx_order_broker_no (broker, broker_order_no);

ALTER TABLE position
    ADD COLUMN broker VARCHAR(10) NOT NULL DEFAULT 'kiwoom',
    ADD INDEX idx_position_broker (broker);

ALTER TABLE fill
    ADD COLUMN broker VARCHAR(10) NOT NULL DEFAULT 'kiwoom',
    ADD COLUMN broker_execution_key VARCHAR(120) NULL,
    ADD UNIQUE INDEX uq_fill_broker_event (broker, broker_execution_key);
```

실제 테이블/컬럼명은 현재 schema를 다시 확인해 조정한다. 기존 `kiwoom_ord_no`는 즉시 삭제하거나 rename하지
않고 compatibility 컬럼으로 남긴다. 첫 전환에서는 position 기본키를 broker 복합키로 바꾸지 않고,
“같은 종목 한 broker” 규칙을 repository와 preflight에서 강제한다.

## 8. repository 변경

raw SQL은 repository에만 둔다.

- order 생성 시 선택된 broker를 고정한다.
- 주문번호 조회는 `(broker, broker_order_no)`를 사용한다.
- fill dedup은 `(broker, broker_execution_key)`를 사용한다.
- 열린 position/order를 읽을 때 broker를 누락하지 않는다.
- reconcile은 다른 broker의 row를 수정하지 않는다.
- 기존 row는 migration default로 `kiwoom`을 갖는다.

`broker_execution_key`는 KIS 체결번호가 안정적으로 제공되면 해당 값을 사용하고, 그렇지 않으면 공식 필드
조합을 versioned 함수로 만든다. 충돌 가능성이 있는 단순 timestamp 조합은 금지한다.

## 9. 잔고·체결 pagination과 대조

KIS 조회는 응답 한 페이지로 끝난다고 가정하지 않는다.

- `tr_cont`와 context key를 끝까지 전달한다.
- 페이지 간 주문번호/체결번호 중복을 dedup한다.
- 조회 기준일, 시작/종료시각, venue를 요청 객체에 명시한다.
- 잔고의 주문가능수량, 평균단가, 평가금액과 현금의 의미를 현재 내부 DTO에 매핑한다.
- 정규장/NXT 거래가 같은 영업일에 섞일 때 시간대와 거래일 기준을 테스트한다.

## 10. 기존 소비자 연결

Phase 3에서는 factory와 adapter까지만 연결하고 polling 동작은 유지한다.

- `signal_executor.py`: `BrokerClient.place_order()` 사용.
- `monitor.py`: 매도 주문 시 같은 broker client 사용.
- `fill_sync.py`: `get_executions()` 사용.
- `order_maintenance.py`: `get_open_orders()`, revise/cancel 사용.
- `reconciliation.py`, `settle.py`: balance/cash/PnL DTO 사용.

`trading/core/execution_engine.py`는 민감 파일이다. 실제 DI 변경 전에 사용자 승인을 받고, 주문 의도·리스크
검사·멱등성은 변경하지 않으며 client 호출부만 최소 수정한다.

## 11. 구현 순서

1. 현재 broker client 메서드와 소비자 호출 계약 inventory.
2. DTO/Protocol/factory와 Kiwoom adapter 구현, 기본 provider 회귀 확인.
3. KIS read-only account 기능(balance/cash/open orders/executions/PnL) 구현.
4. broker 컬럼 migration과 repository 보강.
5. KIS paper buy/sell, revise/cancel 구현.
6. timeout ambiguous 처리와 주문조회 대조 구현.
7. 소비자별 factory 주입.
8. 모의계좌에서 전체 주문 lifecycle 검증.

## 12. 검증 시나리오

- 매수 접수 → 미체결 → 부분체결 → 전량체결.
- 매도 접수 → 부분체결 → 잔량 취소.
- 미체결 주문 가격 정정.
- 이미 전량체결된 주문 취소 요청.
- 주문 거부, 잔고 부족, 주문 가능 시간 외, NXT 미지원 종목.
- HTTP timeout 직후 주문조회에 접수 주문이 있는 경우/없는 경우.
- pagination 2페이지 이상과 페이지 경계 중복.
- 동일 체결 이벤트를 두 번 반영해도 fill/position이 한 번만 변함.
- `BROKER_PROVIDER=kiwoom`의 기존 테스트와 dry-run 결과 불변.

## 13. 완료 기준 (DoD)

- [ ] broker Protocol이 현재 모든 주문·계좌 소비자를 표현한다.
- [ ] 기존 키움 client가 adapter 뒤에서 동일하게 동작한다.
- [ ] KIS 모의계좌에서 buy/sell/revise/cancel 전체 lifecycle이 확인됐다.
- [ ] 주문 timeout에서 무조건 재전송하지 않고 ambiguous 상태가 기록된다.
- [ ] broker/order org/exchange/execution key가 DB에 저장된다.
- [ ] 다른 broker의 order/position을 repository가 오염시키지 않는다.
- [ ] KIS 실패가 키움 실주문으로 자동 fallback되지 않는다.
- [ ] 민감 파일 변경은 별도 사용자 승인 후 최소 범위로 수행됐다.

## 14. 위험과 대응

| 위험 | 대응 |
|---|---|
| timeout 뒤 중복 주문 | 자동 재시도 금지, 주문조회 대조, ambiguous 상태 |
| 주문번호만 저장해 정정취소 실패 | 주문번호와 주문조직번호 함께 저장 |
| paper/live TR 혼합 | 환경별 endpoint/TR mapping 테스트와 startup validation |
| NXT 주문구분 오매핑 | 실전 소액 canary 전까지 미확인 조합 차단 |
| broker 컬럼 누락으로 교차 수정 | repository query에 broker 필수, migration default |
| 전략 로직까지 함께 변경 | broker 호출 경계만 수정, 리스크·전략 의미 고정 |
