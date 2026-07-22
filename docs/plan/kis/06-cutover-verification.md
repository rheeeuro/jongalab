# Phase 6 — 검증, 전환, rollback

## 1. 목표

KIS 조회와 자동매매 경로를 한 번에 켜지 않고 shadow, 모의투자, 제한된 실전 canary를 거쳐 독립적으로
기본화한다. 각 단계는 명시적인 진입·통과·rollback 조건을 갖는다.

공수나 달력 일정이 아니라 관측 결과로 전환 여부를 결정한다.

## 2. 전환 단위

두 provider를 별도 release로 다룬다.

```text
Release A: MARKET_DATA_PROVIDER
  fixture → endpoint shadow → 분석 dry-run → kis 기본화

Release B: BROKER_PROVIDER
  fixture → stream shadow → KIS paper → KRX canary → NXT canary
  → 제한 유니버스 → kis 기본화
```

조회 공급자를 rollback해도 KIS broker는 계속 쓸 수 있고, broker를 rollback해도 KIS 조회 서버는 유지할 수
있다. 다만 열린 포지션/주문이 있으면 broker 전환은 단순 설정 변경으로 처리하지 않는다.

## 3. 공통 사전 조건

- KIS 실전·모의 앱키, HTS ID, 국내주식 계좌와 상품코드가 준비됨.
- paper/live endpoint와 TR mapping이 startup validation을 통과함.
- 모든 schema migration의 forward/rollback 절차가 검토됨.
- KIS와 키움 프로세스가 동시에 설치되어 있지만 실주문 owner는 하나임.
- 로그 마스킹, alert 채널, kill switch, 수동 주문 확인 절차가 준비됨.
- 시스템 시각과 Asia/Seoul timezone이 정상이며 장 상태 판정이 검증됨.
- 운영자가 현재 provider, stream health, open orders, position broker를 한 화면/명령으로 확인 가능함.

## 4. Stage A — fixture와 오프라인 테스트

실제 계좌 호출 전에 다음 fixture를 고정한다.

- KIS REST 성공, 빈 결과, 오류, pagination, rate limit.
- 주문 접수/거부, 정정/취소, 부분체결/전량체결 응답.
- KRX/NXT/통합 quote message.
- 실전/모의 암호화 주문·체결통보.
- PINGPONG, subscribe ack/error, malformed message.

통과 기준:

- 필수 parser/adapter branch가 fixture로 실행된다.
- 민감 정보가 fixture와 snapshot에 없다.
- 같은 event를 반복해도 DB 결과가 한 번만 변한다.
- 키움 provider 회귀 테스트가 유지된다.

## 5. Stage B — 조회 데이터 shadow

### 실행

- 대표 종목군과 실제 종가베팅 요청을 KIS/키움 양쪽에 read-only 실행한다.
- [02-market-data-migration.md](02-market-data-migration.md)의 diff 테이블에 필드·단위·시점 차이를 저장한다.
- KIS 결과로 별도 dry-run 분석을 수행하되 `selected`, report, signal의 운영 row를 덮어쓰지 않는다.

### 통과 기준

- `required` 필드의 미해결 `missing`, `type`, `sign`, `unit` diff가 0이다.
- 가격·거래량·수급 차이는 문서화된 시점/시장 허용범위 안이다.
- chart의 날짜 순서, candle 수, 수정주가 의미가 일치한다.
- rank/universe 차이는 원인이 설명되고 전략 영향이 승인됐다.
- KIS dry-run 후보 차이가 필드 차이로 추적 가능하다.
- 테마 등 미지원 endpoint는 `kiwoom_fallback`으로 명시된다.
- 최소 연속 5거래일 장중·장후 shadow에서 새로운 미설명 diff가 없다.

### 전환

`MARKET_DATA_PROVIDER=kis`로 바꾸되 첫 운영일에는 주문 신호 생성 직전 결과를 키움 dry-run과 다시 대조한다.
문제가 있으면 `kiwoom`으로 되돌린다. 데이터 provider rollback은 주문 broker 상태와 독립적이다.

## 6. Stage C — WebSocket shadow

### 실행

- `trading-kis-stream`을 연결하지만 주문 의사결정 handler는 비활성화한다.
- 실제 보유/후보 종목의 시세를 구독하고 기존 polling 가격과 비교한다.
- KIS 계좌에 발생한 수동/모의 주문으로 주문·체결통보를 inbox에 저장하되 운영 order를 수정하지 않는다.
- 주기 REST 조회로 WS 이벤트 누락 여부를 대조한다.

### 통과 기준

- reconnect 후 구독 복원과 REST catch-up이 자동 수행된다.
- PINGPONG timeout과 stale 판정이 장 상태에 맞게 동작한다.
- quote venue·가격·event time이 polling snapshot과 설명 가능한 범위다.
- REST에서 확인된 주문·체결이 모두 WS 또는 catch-up으로 inbox에 존재한다.
- 중복 처리로 fill/order/position이 두 번 변한 사례가 0이다.
- 구독 상한과 process memory/DB write가 운영 한도 안이다.
- 토큰, 계좌 전체번호, AES key/IV가 로그·DB에 노출되지 않는다.

## 7. Stage D — KIS 모의투자 전체 cycle

다음 lifecycle을 자동매매 워커를 통해 수행한다.

1. 신호 수신과 seed allocation.
2. KRX 매수 접수·부분체결·전량체결.
3. 미체결 정정·취소.
4. position 생성과 quote event 감시.
5. 손절/스탑/트레일링 또는 정규 청산 매도.
6. fill·position·실현손익 반영.
7. 장마감 reconcile과 settle.
8. worker/stream 강제 재시작 후 복구.

모의투자에서 NXT나 특정 주문유형이 지원되지 않으면 해당 항목은 실전 canary 전까지 “미검증”으로 남기고
코드에서 차단한다. 모의 성공을 실전 TR/유동성 동등성의 증거로 간주하지 않는다.

통과 기준:

- 모든 order가 `client_order_key`, broker order no, fill로 추적된다.
- 부분체결 수량 합과 position 수량이 일치한다.
- timeout 뒤 중복 주문이 없다.
- stream 단절 중 체결이 reconnect REST catch-up으로 복구된다.
- stream unhealthy 상태에서 신규 매수가 차단된다.
- 3회 이상의 전체 자동 cycle에서 미해결 reconcile issue가 없다.

## 8. Stage E — 실전 KRX 소액 canary

### 범위

- 사전 지정한 유동성 높은 종목 1개.
- 사전 지정한 최소 수량.
- KRX 지정가부터 시작하고 시장가·정정·취소를 순차 확인.
- 기존 일일 risk limit보다 더 낮은 canary 전용 상한.
- 운영자 입회와 즉시 수동 취소/청산 가능 상태.

### 중단 조건

- broker/local 주문·체결·position 불일치.
- 주문 timeout 뒤 접수 여부 판단 불가.
- 중복 주문 또는 중복 매도 의도.
- WebSocket 체결 누락이 REST catch-up으로도 해결되지 않음.
- 잘못된 venue, 수량, 주문유형, 계좌 사용.
- stream stale인데 신규 매수가 실행됨.

하나라도 발생하면 신규 주문을 중단하고 열린 KIS 주문/position을 KIS에서 정리한 뒤 원인을 분석한다.

## 9. Stage F — NXT canary

KRX 검증과 별도로 수행한다.

- NXT 거래 가능 종목 확인.
- 지정가 → 정정/취소 → 프로젝트가 실제 사용하는 최유리 IOC 순서로 검증.
- KIS 주문 응답의 venue와 실제 체결 시장 대조.
- KRX/NXT 동시 호가 시간대의 effective price 선택 확인.
- SOR 주문을 사용할 경우 주문 route와 체결 venue를 구분 저장.

NXT 주문구분/체결통보/잔고 계약이 확정되지 않으면 `BROKER_PROVIDER=kis` 기본화와 별개로 NXT 자동주문을
feature flag로 차단하고 KRX만 운영한다.

## 10. Stage G — 제한 유니버스 운영

- 허용 종목 whitelist 또는 최대 동시 position 수를 둔다.
- canary 전용 주문금액 상한을 유지한다.
- 매 거래일 시작 전 balance/open orders/executions reconcile을 확인한다.
- 장중 stream health, inbox backlog, quote stale, duplicate count를 관제한다.
- 장마감 broker/local 수량·평균단가·현금·체결·손익을 대조한다.

통과 기준:

- 최소 연속 5거래일 동안 unexplained reconciliation mismatch가 0이다.
- REST에서 발견된 체결 누락이 0이거나 자동 catch-up으로 모두 해소된다.
- duplicate fill/order side effect가 0이다.
- stale 중 신규매수, broker 교차 주문, 잘못된 venue 주문이 0이다.
- 모든 강제 재시작에서 자동 복구 후 healthy 상태로 돌아온다.

## 11. 기본값 전환

통과 후 설정 기본값 후보를 다음과 같이 바꾼다.

```text
MARKET_DATA_PROVIDER=kis
BROKER_PROVIDER=kis
```

단, 코드는 두 provider를 계속 지원하고 운영 문서에 키움 rollback 명령과 확인 순서를 남긴다.
KIS 기본화 뒤에도 키움 토큰·DB·서버를 삭제하지 않는다.

## 12. rollback 절차

### 조회 데이터

1. 신규 분석 worker 시작을 멈춘다.
2. `MARKET_DATA_PROVIDER=kiwoom`으로 변경한다.
3. 키움 health와 대표 endpoint를 확인한다.
4. 분석 dry-run으로 응답 shape를 확인한 뒤 worker를 재개한다.

### broker — 열린 포지션/주문 없음

1. 신규 signal 실행 중단.
2. KIS open orders, executions, balance와 로컬 DB 대조.
3. KIS 열린 주문/position이 0인지 확인.
4. `BROKER_PROVIDER=kiwoom`으로 변경.
5. 키움 계좌 bootstrap/reconcile 후 worker 재개.

### broker — 열린 KIS 포지션/주문 있음

설정만 키움으로 바꾸지 않는다.

1. 신규 매수를 차단한다.
2. KIS 미체결을 취소하거나 정책에 따라 관리한다.
3. 기존 KIS position은 KIS adapter의 reduce-only 경로로 계속 관리한다.
4. 모든 fill과 balance를 reconcile한다.
5. KIS position/order가 0이 된 뒤 다음 거래일부터 키움 broker를 활성화한다.

같은 날 같은 종목을 키움에서 다시 사서 상태를 합치는 행위는 금지한다.

## 13. 필수 관제 항목

| 분류 | 항목 |
|---|---|
| 연결 | connected, healthy, last message, reconnect count |
| 구독 | desired/sent/acknowledged count, rejected subscriptions |
| 시세 | last quote age, event latency, invalid/out-of-order count |
| 이벤트 | inbox pending oldest age, retry/unmatched/duplicate count |
| 주문 | submitted/accepted/partial/filled/rejected/ambiguous count |
| 대조 | broker-local order/fill/position/cash mismatch |
| 안전 | blocked new buys, reduce-only fallback, provider/venue |

alert 메시지는 broker, environment, order/stock 식별자 일부, 오류코드와 운영 조치를 포함하되 비밀을 포함하지
않는다.

## 14. 운영 체크리스트

### 장 시작 전

- [ ] 현재 market data/broker provider 확인.
- [ ] KIS token과 upstream health 확인.
- [ ] stream healthy 및 필수 구독 ack 확인.
- [ ] balance/open orders/executions bootstrap mismatch 0 확인.
- [ ] kill switch와 canary limit 확인.

### 장중

- [ ] quote/event latency와 inbox backlog 확인.
- [ ] ambiguous/rejected/duplicate 주문 확인.
- [ ] stream stale 신규매수 차단 확인.
- [ ] reconcile issue 발생 시 신규 주문 중단.

### 장 종료 후

- [ ] open orders 0 또는 이월 사유 확인.
- [ ] fill 합계와 position 수량 대조.
- [ ] broker/local 현금·손익 차이 확인.
- [ ] 다음 거래일 차단 사유와 미해결 issue 확인.

## 15. 최종 완료 기준 (DoD)

- [ ] KIS 조회 23종의 지원/fallback 상태와 내부 계약이 확정됐다.
- [ ] `MARKET_DATA_PROVIDER=kis`가 승인된 shadow 기준을 통과했다.
- [ ] KIS paper에서 전체 자동매매 lifecycle과 재시작 복구가 검증됐다.
- [ ] KRX와 실제 사용 NXT 주문유형 canary가 각각 통과했다.
- [ ] 제한 운영에서 중복 side effect와 미해결 reconcile mismatch가 없다.
- [ ] provider 전환·rollback runbook을 운영자가 실행해 봤다.
- [ ] 키움 API, DB, 클라이언트, PM2 경로가 삭제되지 않았다.
- [ ] README, schema, PM2, 환경변수 문서와 실제 동작이 일치한다.

## 16. 실패를 숨기지 않는 규칙

- 검증하지 못한 주문유형은 “지원”으로 표시하지 않는다.
- 모의투자 성공을 NXT 실전 성공으로 간주하지 않는다.
- WebSocket에서 못 본 체결을 REST가 발견하면 누락 metric을 0으로 덮지 않는다.
- 허용 diff는 이유·범위·승인자를 기록한다.
- rollback은 실패가 아니라 설계된 정상 경로이며, 키움 자산을 보존하는 이유다.
