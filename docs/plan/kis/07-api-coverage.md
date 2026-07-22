# 부록 — 키움 기능별 KIS API coverage

> 이 문서는 구현 중 갱신하는 대응표다. `직접`은 공식 KIS 카테고리에 대응 기능이 확인된 경우,
> `조합/파생`은 여러 조회 또는 로컬 계산이 필요한 경우, `실응답 검증`은 이름이 같아도 현재 전략의
> 시점·필드·단위를 비교해야 하는 경우, `키움 fallback`은 KIS 1:1 대응이 확인되지 않은 경우다.

## 1. 조회 API 23종

현재 외부 계약(`/stock/*`, `/chart/*` 등)은 먼저 유지하고 내부 adapter만 교체한다. KIS 원본 응답을
그대로 반환해 모든 소비자를 동시에 고치는 방식은 사용하지 않는다.

| # | 현재 경로 | 키움 TR | KIS 후보 | 판정 | 구현·확인사항 |
|---:|---|---|---|---|---|
| 1 | `/stock/basic-info` | ka10001 | 주식현재가 시세 + 상품/주식기본조회 | 조합/검증 | 현재가·시총·52주 고저·누적거래대금 |
| 2 | `/stock/detail-info` | ka10100 | 상품기본조회 + 종목 마스터 | 조합/검증 | 시장명·업종·NXT 가능 여부 |
| 3 | `/stock/order-book` | ka10004 | 주식현재가 호가/예상체결 | 직접/검증 | KRX/NXT/통합과 10호가 잔량 단위 |
| 4 | `/stock/broker` | ka10002 | 주식현재가 회원사/회원사 종목매매동향 | 직접/검증 | 상위 5 매수·매도, 외국계 구분 |
| 5 | `/stock/list` | ka10099 | KIS 종목정보 master file | 배치 대체 | 시장·ETF·ETN·NXT 코드와 갱신 실패 대응 |
| 6 | `/stock/intraday-investor` | ka10059 | 주식현재가 투자자/외인기관 추정집계 | 직접/검증 | 개인·기관·외국인 당일 순매수와 시점 |
| 7 | `/stock/short-sale-trend` | ka10014 | 공매도 일별추이 | 직접 | 수량·거래대금·비중 단위 |
| 8 | `/stock/lending-trend` | ka20068 | 종목별 일별 대차거래추이 | 직접 | 체결/상환/잔고 정규화 |
| 9 | `/stock/credit-trend` | ka10013 | 신용잔고 일별추이 | 직접 | 융자/대주, 잔고율, 일자 정렬 |
| 10 | `/stock/execution-strength-hourly` | ka10046 | 당일 시간대별체결/실시간체결 | 조합/검증 | 5/20/60분 평균과 체결강도 산식 |
| 11 | `/stock/execution-strength-daily` | ka10047 | 일자별 체결 + 로컬 집계 | 조합/검증 | 5/20/60일 평균 직접 제공 여부 |
| 12 | `/stock/after-hours-price` | ka10087 | 시간외현재가/호가/시간별체결 | 직접/검증 | 시간외 단일가와 NXT 구분 |
| 13 | `/chart/daily` | ka10081 | 국내주식 기간별시세 | 직접 | 수정주가, 연속조회, 정렬 |
| 14 | `/chart/minute-pages` | ka10080 | 당일분봉 + 일별분봉 | 조합/검증 | 과거일 범위, page 크기, venue |
| 15 | `/rank/trading-value` | ka10032 | 거래량/거래대금 순위 계열 | 실응답 검증 | 거래대금 기준 top N 재현 |
| 16 | `/market/after-close-investor` | ka10066 | 시장별 + 종목별 투자자 일별 | 조합/검증 | 장마감 확정치와 전체 종목 목록 |
| 17 | `/rank/after-hours-flu` | ka10098 | 시간외등락률순위 | 직접 | ETF/ETN 제외와 상승/하락 정렬 |
| 18 | `/program-trade/by-stock` | ka90004 | 프로그램매매 종합현황 | 직접/검증 | 시장 전체 종목과 현재 shape |
| 19 | `/program-trade/daily-trend` | ka90013 | 종목별 프로그램매매추이 일별 | 직접 | 순매수 금액·수량과 범위 |
| 20 | `/program-trade/hourly-trend` | ka90008 | 종목별 프로그램매매추이 체결 | 직접/검증 | `until_tm`, pagination, 누적 차분 |
| 21 | `/inst-foreign/consecutive` | ka10131 | 기관·외국인 가집계 + 일별동향 | 조합/파생 | 연속 순매수 일수·금액 로컬 계산 |
| 22 | `/theme/groups` | ka90001 | 공식 1:1 대응 미확인 | **키움 fallback** | 그룹 ID·등락률·구성 수 의미 유지 |
| 23 | `/theme/stocks` | ka90002 | 공식 1:1 대응 미확인 | **키움 fallback** | 기존 점수/섹터 영향, 빈값 대체 금지 |

### 우선 실응답 검증 묶음

다음 항목은 adapter 확정 전에 실제 응답과 소비 코드를 함께 비교한다.

1. NXT 가능 종목 판별과 venue 코드.
2. 거래대금 상위 50과 시장/상품 필터.
3. 당일 개인·기관·외국인 수급의 시점과 금액 단위.
4. 기관·외국인 연속 매매 현황 계산.
5. 당일/일별 체결강도 산식.
6. 프로그램 오전/오후 누적 순매수.
7. 장마감 후 확정 수급.
8. 과거 거래일 1분봉과 NXT 체결가.

## 2. 조회 endpoint 공통 계약

각 endpoint 항목에 구현 전에 다음 속성을 채운다.

| 속성 | 내용 |
|---|---|
| `capability` | `kis`, `kiwoom_fallback`, `not_used` |
| `required_fields` | 실제 소비자가 읽는 필수 필드 |
| `source_timestamp` | 값의 기준 시각/확정 시각 |
| `venue_scope` | KRX, NXT, 통합, 시장 전체 |
| `unit/sign` | 원, 천원, 주, %, 양수/음수 규칙 |
| `pagination` | 연속조회 key와 최대 범위 |
| `empty_semantics` | 데이터 없음과 값 0의 구분 |
| `shadow_tolerance` | 허용 오차·시차와 근거 |

KIS에 필수값이 없으면 0을 만들어 성공 응답으로 반환하지 않는다. derived 필드는 산식과 rounding을 테스트로
고정하고, 미지원은 `source=kiwoom_fallback`을 표시한다.

## 3. 주문·계좌 API

| 내부 기능 | 키움 | KIS 후보 | 내부 계약에서 추가할 것 | 필수 확인 |
|---|---|---|---|---|
| `buy()` | kt10000 | 현금주문, 실전 TTTC0012U | broker, venue, order no/org no | KRX/NXT 주문구분, paper TR |
| `sell()` | kt10001 | 현금주문, 실전 TTTC0011U | 동일 | 시장가 가격 파라미터, 잔량 |
| `modify()` | kt10002 | 정정취소, 실전 TTTC0013U | original order identifiers | 정정 가능 수량, 주문조직번호 |
| `cancel()` | kt10003 | 정정취소, 실전 TTTC0013U | original order identifiers | 부분체결 잔량 취소 |
| `get_balance()` | kt00018 | 주식잔고조회, TTTC8434R 계열 | broker, venue, available qty | 실전/모의 page, NXT 구분 |
| `get_deposit()` | kt00001 | 매수가능조회 TTTC8908R + 잔고 summary | cash DTO | 종목/가격 없는 가용현금 의미 |
| `get_daily_realized_pnl()` | ka10074 | 기간별/일별 실현손익 | fee/tax basis | 거래일 귀속, 비용 포함 기준 |
| `get_open_orders()` | ka10075 | 일별주문체결/정정취소가능주문 | cursor, venue, org no | KRX/NXT/SOR/ALL, pagination |
| `get_executions()` | ka10076 | 일별주문체결조회 + WS 통보 | execution key | 부분체결, 조회기간, pagination |

KIS 응답의 `rt_cd`, `msg_cd`, `msg1`, `output`은 broker adapter에서 다음 의미로 정규화한다.

```text
BrokerOrderResult
  accepted: bool
  broker: "kis" | "kiwoom"
  order_no: str | null
  order_org_no: str | null
  stk_cd: str
  requested_qty: int
  message_code: str
  message: str
  raw: masked dict
```

원본 전체 응답을 그대로 audit log에 남기지 않는다. 계좌, 토큰, 앱키를 제거한 정규화 응답만 기록한다.

## 4. 실시간 API

| 목적 | KIS TR | 적용 | 구현 확인사항 |
|---|---|---|---|
| KRX 실시간 체결가 | H0STCNT0 | 보유·주문 종목 감시 | field order, 체결시각, 가격 부호 |
| NXT 실시간 체결가 | H0NXCNT0 | NXT 시간대 감시 | NXT 가능종목, 거래일/venue |
| 통합 실시간 체결가 | H0UNCNT0 | shadow 후 선택 | 체결 venue 식별과 기존 시간대 규칙 parity |
| KRX 호가 | H0STASP0 | 첫 전환 비범위 | 추후 호가 기반 주문에만 사용 |
| NXT 호가 | H0NXASP0 | 첫 전환 비범위 | 구독 한도와 venue 검증 |
| 통합 호가 | H0UNASP0 | 첫 전환 비범위 | route/venue 의미 검증 |
| 실전 주문·체결통보 | H0STCNI0 | order/fill 주경로 | AES, 접수/체결 구분, 부분체결 |
| 모의 주문·체결통보 | H0STCNI9 | paper 검증 | 실전 필드/상태 차이 |

주문·체결통보는 subscription 응답의 AES key/IV로 복호화한다. 접수·거부·정정·취소·부분체결·전량체결을
분리하고 안정적인 event key를 만든다.

WebSocket 등록 한도는 공식 포털의 최신 값을 구현 시작 시 재확인한다. 내부 상한은 공식 한도보다 낮게 두고,
전 후보가 아니라 열린 position·미체결·실제 매수 후보만 구독한다.

## 5. 소비자 영향도

| 영역 | 주요 소비자 | 계획 |
|---|---|---|
| 점수/후보 선정 | `trading_engine.py`, `closing_bet.py` | adapter parity, `closing_bet`에서 provider 주입 |
| 갭·결과 라벨 | `gap_check.py`, `daily_ohlc.py`, `after_hours_labels.py` | KRX/NXT 시점·분봉 정렬 회귀 |
| 종목·섹터 | `ticker.py`, `sector_resolver.py`, `news_ticker_seed.py` | master file, 업종, NXT 가능 여부 |
| 시장 화면 | market data router/UI | 현재 내부 shape 유지해 변경 최소화 |
| 주문 | `execution_engine.py`, `signal_executor.py`, `monitor.py` | broker DTO와 주문유형 mapper 사용 |
| 체결/정합성 | `fill_sync.py`, `order_maintenance.py`, reconcile 계열 | event projector + REST catch-up |

## 6. 구현 중 확정해야 할 질문

- KIS 통합 체결가가 현재 시간대별 `get_market_price()`를 정확히 대체하는가.
- NXT 최유리 IOC에 대응하는 주문구분과 실전 체결 동작은 무엇인가.
- 정정·취소에 필요한 주문조직번호가 모든 주문/통보/조회 경로에 존재하는가.
- 주문·체결통보에서 부분체결마다 고유한 체결번호를 안정적으로 얻을 수 있는가.
- 무종목 “예수금” 계약을 어느 KIS 조회 조합으로 구현할 것인가.
- 프로그램매매와 투자자 수급의 KRX/NXT/SOR 포함 범위는 무엇인가.
- 거래대금 순위가 키움과 같은 상품·시장 유니버스를 지원하는가.
- 테마 기능은 키움 fallback을 장기 유지할 것인가, 별도 데이터 소스를 추후 선정할 것인가.

## 7. coverage 완료 기준

- [ ] 조회 23종 각각 `kis`, `kiwoom_fallback`, `not_used`가 확정됐다.
- [ ] 모든 `required` 필드에 KIS source, 단위, 시점, venue가 연결됐다.
- [ ] 주문·계좌 9개 기능의 실전/모의 TR과 pagination이 확인됐다.
- [ ] 실제 사용 주문유형의 KRX/NXT mapping이 paper/canary로 검증됐다.
- [ ] WS TR별 fixture, field order, event key 규칙이 테스트에 고정됐다.
- [ ] 미지원 기능이 조용히 빈값/0으로 대체되지 않는다.
- [ ] 데이터 provider 전환이 broker provider를 자동 변경하지 않는다.

## 8. 공식 자료

- [KIS Developers API 서비스 목록](https://apiportal.koreainvestment.com/apiservice-summary)
- [공식 Open Trading API 저장소](https://github.com/koreainvestment/open-trading-api)
- [국내주식 REST 함수 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/domestic_stock/domestic_stock_functions.py)
- [국내주식 WebSocket 함수 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/domestic_stock/domestic_stock_functions_ws.py)
- [현금주문 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_cash/order_cash.py)
- [정정취소 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_rvsecncl/order_rvsecncl.py)
- [잔고조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/inquire_balance.py)
- [일별주문체결조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)
