# KIS 전환 구현 계획 — 키움 보존, KIS 기본화, 자동매매 WebSocket 전환

> 작성: 2026-07-22. 이 디렉터리는 키움 기반 국내주식 데이터·주문 경로를 KIS로 병행 이관하고,
> 자동매매의 시세·주문·체결 감시를 polling 중심에서 WebSocket 중심으로 전환하기 위한 전체 구현 계획이다.
> 일정과 공수 산정은 포함하지 않으며, 각 단계의 세부 구현은 번호 문서(01~07)에 정의한다.

---

## 1. 목표와 완료 상태

완료 후 기본 운영 경로는 다음과 같다.

- `kis/:8003`이 국내주식 조회 데이터를 제공한다.
- `trading`은 KIS REST로 주문·정정취소·잔고·체결내역을 처리한다.
- `trading-kis-stream` 단일 프로세스가 KIS WebSocket 연결과 구독을 소유한다.
- 보유종목 가격 감시와 주문·체결 반영은 WebSocket 이벤트가 주경로가 된다.
- 시작·재연결·장마감·이상 감지 때는 KIS REST로 상태를 보정한다.
- 기존 `kiwoom/:8001`, 키움 주문 클라이언트, 토큰 DB와 PM2 앱은 삭제하지 않고 rollback 경로로 남긴다.

즉, WebSocket은 REST를 없애는 수단이 아니다. 주문 전송과 복구 가능한 상태 조회는 REST에 남기고,
반복 polling으로 하던 실시간 감지만 이벤트로 바꾼다.

## 2. 현재 결합 지점

| 영역 | 현재 구현 | 전환 시 핵심 문제 |
|---|---|---|
| 조회 데이터 | `kiwoom/:8001`의 POST 엔드포인트 23종 | 점수·피처 코드가 키움 응답 필드명에 결합 |
| 종가베팅 | `KiwoomRestClient`를 `AnalysisEngine`에 전달 | 민감 파일을 바꾸지 않고 provider 주입 필요 |
| 주문 | 키움 `kt10000`~`kt10003` | KIS 계좌·상품코드·거래소·주문번호 계약이 다름 |
| 계좌/체결 | `kt00018`, `kt00001`, `ka10074`~`ka10076` | 연속조회, 원주문번호, 부분체결 정규화 필요 |
| 가격 감시 | `monitor.py`가 15초마다 현재가 조회 | 종목별 실시간 구독과 stale 판단 필요 |
| 체결 동기화 | `fill_sync.py`, `order_maintenance.py` polling | 암호화 체결통보의 멱등 처리와 누락 복구 필요 |
| 기존 KIS | 지수·선물 REST와 야간선물 WS | 인증·PINGPONG·재연결 패턴은 재사용 가능 |

## 3. 목표 아키텍처

```text
                         MARKET_DATA_PROVIDER
                  ┌───────────┴───────────┐
                  ▼                       ▼
          kis/:8003 + adapter      kiwoom/:8001 (보존)
                  │                       │
                  └───────────┬───────────┘
                              ▼
                   provider-neutral data client
                   (현재 내부 응답 계약 유지)

                         BROKER_PROVIDER
                  ┌───────────┴───────────┐
                  ▼                       ▼
             KIS broker REST       Kiwoom broker (보존)
                  │
                  ├── 주문·정정취소·계좌 snapshot
                  └── approval key
                              │
                              ▼
                  trading-kis-stream (WS 1세션)
                  ├── KRX/NXT/통합 실시간 시세
                  ├── 주문·체결통보 복호화
                  ├── durable inbox + dedup
                  └── reconnect REST catch-up
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
       position monitor                 order/fill projector
       손절·스탑·트레일링               order/fill/position/audit
              └───────────────┬────────────────┘
                              ▼
                    REST reconcile + watchdog
```

공급자 스위치는 독립적으로 둔다.

| 설정 | 허용값 | 초기값 | 의미 |
|---|---|---|---|
| `MARKET_DATA_PROVIDER` | `kiwoom`, `kis` | `kiwoom` | 분석·스크리닝 조회 공급자 |
| `BROKER_PROVIDER` | `kiwoom`, `kis` | `kiwoom` | 주문·계좌·체결 공급자 |
| `KIS_DATA_BASE_URL` | URL | `http://127.0.0.1:8003` | 내부 KIS 데이터 서버 주소 |

`KIS_DATA_BASE_URL`은 외부 Open API base URL과 이름을 분리한다. 조회 shadow는 허용하지만 실주문
dual-write는 금지한다.

## 4. 구현 단계

| 단계 | 문서 | 결과물 | 착수 조건 |
|---|---|---|---|
| **Phase 1** | [01-provider-foundation.md](01-provider-foundation.md) | `kis/:8003`, 토큰 소유권, provider 설정·계약 | 즉시 |
| **Phase 2** | [02-market-data-migration.md](02-market-data-migration.md) | 조회 23종 adapter, shadow diff, endpoint별 전환 | Phase 1 |
| **Phase 3** | [03-broker-rest.md](03-broker-rest.md) | KIS 주문·정정취소·계좌 REST adapter | Phase 1, KIS 모의계좌 |
| **Phase 4** | [04-websocket-runtime.md](04-websocket-runtime.md) | 단일 WS runtime, 암호화 통보, inbox·health | Phase 1·3 |
| **Phase 5** | [05-event-driven-trading.md](05-event-driven-trading.md) | monitor/fill 이벤트화, REST catch-up·fallback | Phase 3·4 |
| **Phase 6** | [06-cutover-verification.md](06-cutover-verification.md) | shadow→모의→소액 canary→기본값 전환 | Phase 2·5 |
| **부록** | [07-api-coverage.md](07-api-coverage.md) | 키움 기능별 KIS 대응표와 확인 항목 | 구현 중 상시 갱신 |

순서는 기반 → 조회 → 주문 REST → WebSocket → 소비자 이벤트화 → 전환이다. 조회와 주문은 기반 완료 후
병행할 수 있지만, 기본 공급자 전환은 각 검증 게이트를 통과한 뒤 독립적으로 수행한다.

## 5. 전 단계 공통 설계 원칙

1. **키움 보존**: `kiwoom/` 코드·DB·프로세스·클라이언트를 삭제하거나 KIS 코드로 덮어쓰지 않는다.
2. **내부 계약 고정**: KIS 원본 필드와 TR ID를 전략·워커에 노출하지 않고 adapter에서 정규화한다.
3. **단일 실주문 공급자**: 한 실행에서 한 broker만 주문을 전송한다. provider 전환 중에도 dual-write 금지다.
4. **한 종목 한 broker**: 같은 종목의 열린 포지션을 KIS와 키움에 동시에 보유하지 않는다.
5. **이벤트는 at-least-once**: 중복 수신을 정상으로 보고 durable inbox와 고유 event key로 멱등 처리한다.
6. **REST가 복구 기준**: WebSocket은 빠른 경로이고 REST snapshot/catch-up이 누락 복구와 최종 대조를 담당한다.
7. **연결 장애 시 보수적 동작**: stream이 stale이면 신규 매수는 차단하고, 노출 축소 매도는 REST fallback을 허용한다.
8. **구독 최소화**: 전 종목을 구독하지 않고 열린 포지션·미체결·실제 매수 후보만 동적으로 구독한다.
9. **원본 보존**: 정상화된 필드와 함께 원본 응답/event payload를 감사 가능한 범위에서 저장한다.
10. **명시적 fallback**: 미지원 기능만 endpoint 단위로 키움 fallback한다. timeout이나 KIS 오류를 조용히 키움으로 우회하지 않는다.

## 6. 건드리지 않는 것과 승인 게이트

- `jongalab/core/trading_engine.py`, `jongalab/core/prompts.py`는 수정하지 않는다. `closing_bet.py`의
  client 주입을 provider 중립화해 기존 `AnalysisEngine` 계약을 유지한다.
- `trading/core/risk_engine.py`는 리스크 한도·킬스위치 의미를 바꾸지 않는다.
- `trading/core/execution_engine.py`는 broker 주입을 위해 변경 가능성이 높지만 민감 파일이다.
  실제 구현 전에 사용자에게 변경 파일·범위를 제시하고 별도 승인을 받는다.
- 전략, 선정 기준, 시드 배분, 주문 의도와 청산 시간표는 이번 전환의 범위가 아니다.
- KIS를 기본값으로 바꾸더라도 키움 자산은 자동 삭제·마이그레이션하지 않는다.

## 7. 명시적 비범위

- 키움 API·DB·PM2 앱 제거.
- 두 증권사 동시 주문, 스마트 주문 라우팅, 브로커 간 포지션 자동 이전.
- 전 종목 틱 저장소나 시세 재배포 플랫폼 구축.
- 전략 점수·손절률·트레일링·시드 배분 로직 변경.
- KIS에 1:1 대응이 확인되지 않은 테마 기능의 새 외부 데이터 소스 도입. 이 기능은 키움 fallback으로 둔다.
- WebSocket 연결만 믿고 REST reconcile을 제거하는 작업.

## 8. 공통 완료 기준

각 Phase는 해당 문서의 DoD와 함께 다음 조건을 만족해야 한다.

1. Python 변경 파일마다 `uv run --directory <project> python -m py_compile <file>` 통과.
2. parser·adapter·dedup·상태 전이는 fixture 기반 단위 테스트 추가 및 통과.
3. 라우터 변경은 API 기동 후 status와 response shape 확인.
4. 워커는 단발/모의 실행으로 로그, DB 반영, 재시작 복구 확인.
5. 스키마는 정본 create SQL과 번호 마이그레이션을 함께 갱신.
6. 주요 로직 변경 시 `kis/README.md`, `trading/README.md`, `jongalab/README.md` 동기화.
7. 로그와 DB에 앱키·시크릿·토큰·계좌 전체번호·WebSocket AES key/IV가 노출되지 않음.
8. `MARKET_DATA_PROVIDER=kiwoom`, `BROKER_PROVIDER=kiwoom` 회귀 경로가 계속 동작함.

## 9. 공식 기준 자료

- [KIS Developers API 서비스 목록](https://apiportal.koreainvestment.com/apiservice-summary)
- [한국투자증권 공식 Open Trading API GitHub](https://github.com/koreainvestment/open-trading-api)
- [공식 국내주식 WebSocket 함수 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/domestic_stock/domestic_stock_functions_ws.py)
- [공식 현금주문 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_cash/order_cash.py)
- [공식 잔고조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/inquire_balance.py)
- [공식 일별주문체결조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)
- [공식 정정취소 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_rvsecncl/order_rvsecncl.py)
- [KIS WebSocket 등록 한도 안내](https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000001/post/d0d1a83f-6f8d-4437-9700-6d26702fd989)

TR ID, 주문구분 코드, 응답 필드와 유량 제한은 변경될 수 있으므로 각 Phase 구현 시작 시 공식 샘플과
포털을 다시 확인하고 [07-api-coverage.md](07-api-coverage.md)를 갱신한다.
