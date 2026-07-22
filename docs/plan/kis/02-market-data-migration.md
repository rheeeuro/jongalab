# Phase 2 — 국내주식 조회 데이터 KIS 이관

## 1. 목표

`kiwoom/:8001`이 제공하는 국내주식 조회 endpoint 23종을 `kis/:8003`에 구현하고, 현재 분석 코드가
읽는 내부 응답 계약으로 정규화한다. 운영 전환은 endpoint별 shadow 비교가 끝난 뒤 수행한다.

이 단계의 핵심은 “KIS 응답을 그대로 전달”하는 것이 아니라 “전략이 의존하는 의미와 단위를 보존”하는
것이다. KIS에 대응 기능이 없으면 명시적으로 키움 fallback 대상으로 남긴다.

## 2. 응답 계약 고정

현재 소비자가 키움 원본 필드명을 직접 읽고 있으므로 첫 이관에서 모든 전략 코드를 동시에 바꾸지 않는다.

```text
KIS upstream response
        │
        ▼
kis/core/kis_api/*        원본 요청·pagination
        │
        ▼
kis/core/adapter.py       단위·부호·날짜·시장·필드명 정규화
        │
        ▼
kis/:8003 endpoint        현재 kiwoom/:8001 내부 계약과 호환
        │
        ▼
jongalab KisDataClient    MarketDataClient Protocol 구현
```

KIS adapter는 현재 필요한 필드만 생성하되 누락을 `0`이나 빈 문자열로 숨기지 않는다. 필수 필드가 없으면
`DATA_CONTRACT_ERROR`로 실패하고 shadow diff에 남긴다. 향후 provider-neutral 영문 DTO로 바꾸는 작업은
KIS 기본화 이후 별도 리팩터링으로 분리한다.

## 3. 구현 파일

```text
kis/core/kis_api/
├── base.py
├── stock.py             # 기본정보·현재가·거래원·프로그램
├── chart.py             # 일/분/틱 차트와 pagination
├── supply.py            # 기관·외국인·개인·순매수
├── risk_label.py        # 투자주의·경고·거래정지 등
├── rank.py              # 거래량·등락률·기관외국인 순위
└── index_future.py      # 기존 KIS 지수·선물 기능 흡수
kis/core/adapter.py      # Kiwoom-compatible response 변환
kis/api.py               # read-only routes
jongalab/core/kis_data_client.py
jongalab/core/market_data_client.py
jongalab/core/repository/market_data_shadow.py
jongalab/workers/kis_market_data_shadow.py
jongalab/sql/34. migrate_kis_shadow_diff.sql
```

정확한 endpoint와 KIS 후보 API는 [07-api-coverage.md](07-api-coverage.md)를 정본으로 삼는다.

## 4. 구현 배치

### Batch A — 종목 기본·현재가·차트

- 종목 기본정보와 현재가.
- 일봉, 분봉, 틱 차트.
- 전일종가, 등락률, 거래량, 거래대금, OHLC, 체결시각.
- 연속조회가 필요한 차트는 iterator로 모두 수집하되 최대 페이지/기간을 endpoint별로 제한한다.

검증 포인트:

- 가격 부호와 절대값 처리.
- KRX/NXT/통합 현재가의 시장 기준.
- 수정주가 적용 여부와 일자 정렬 방향.
- 분봉/틱의 장 구분과 timezone.

### Batch B — 수급·프로그램·거래원

- 기관/외국인/개인 매매동향.
- 프로그램 순매수와 시계열.
- 외국인 보유율·기관/외국인 연속 순매수.
- 거래원별 매수/매도 정보.

검증 포인트:

- 수량과 금액 단위, 순매수 부호.
- 당일 잠정치와 확정치의 시점 차이.
- 시장별 데이터 포함 범위.
- 개인 값이 직접 제공되지 않을 때 계산식과 반올림 규칙.

### Batch C — 순위·위험 라벨

- 거래량, 거래대금, 등락률, 기관/외국인 순매수 순위.
- 투자주의/경고/위험, 단기과열, 거래정지 등 전략 필터에 쓰는 라벨.

검증 포인트:

- ETF/ETN/스팩 포함 여부.
- 코스피/코스닥 시장 필터.
- 순위 상한과 pagination.
- 라벨의 효력 시작일·종료일과 장중 갱신 시각.

### Batch D — 테마·특수 기능

KIS 공식 API에서 키움 테마 그룹/구성종목과 의미가 같은 기능을 확인하지 못하면 이 endpoint는
`source=kiwoom_fallback`으로 명시한다. fallback은 다음 규칙을 따른다.

1. 코드에 endpoint별 지원표를 둔다.
2. KIS timeout·429·5xx를 이유로 자동 fallback하지 않는다.
3. 응답 metadata에 실제 provider를 포함한다.
4. fallback 사용량을 metric/log로 집계한다.
5. 추후 대체 데이터 소스를 도입하더라도 같은 내부 계약을 구현한다.

## 5. 시장 선택 규칙

현재 시간대별 KRX/NXT 선택 로직을 문서화하고 adapter 한 곳에 둔다.

| 시점/용도 | 기본 venue | 대체 규칙 |
|---|---|---|
| KRX 정규장 분석 | KRX | KRX 최신 체결/호가 사용 |
| NXT 프리·애프터 분석 | NXT | 해당 종목 NXT 미지원 시 상태를 명시하고 KRX snapshot 사용 |
| 일반 현재가 | 통합/SOR 대응 시세 | KIS 통합 값의 의미 검증 전에는 기존 시간대 규칙 유지 |
| 일봉·수급·순위 | API가 정의한 정규시장 범위 | metadata에 기준 시장·시점 기록 |

KIS 통합 체결가가 기존 `get_market_price()` 의미와 동일하다는 실측이 끝나기 전에는 시간대별 규칙을
바꾸지 않는다.

## 6. shadow 비교 저장소

`jongalab/sql/34. migrate_kis_shadow_diff.sql`에 임시 감사 테이블을 추가한다.

```sql
CREATE TABLE market_data_shadow_diff (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    captured_at     DATETIME(6) NOT NULL,
    endpoint        VARCHAR(80) NOT NULL,
    stk_cd          VARCHAR(20) NULL,
    field_name      VARCHAR(80) NOT NULL,
    kiwoom_value    TEXT NULL,
    kis_value       TEXT NULL,
    diff_kind       VARCHAR(30) NOT NULL,
    accepted        TINYINT(1) NOT NULL DEFAULT 0,
    detail          JSON NULL,
    INDEX idx_shadow_endpoint_time (endpoint, captured_at),
    INDEX idx_shadow_stock_time (stk_cd, captured_at)
);
```

`diff_kind`는 최소 `missing`, `type`, `sign`, `unit`, `value`, `ordering`, `timing`, `universe`를 사용한다.
원본 전체 payload를 행마다 복제하지 않고 요청 ID, source timestamp, 비교 요약만 `detail`에 둔다.

## 7. shadow worker 흐름

```text
representative request set
        │
        ├── KiwoomRestClient ──┐
        └── KisDataClient ─────┤
                               ▼
                    endpoint-specific comparator
                    ├── key/row 정렬
                    ├── 단위·부호 비교
                    ├── 허용 시차·오차 적용
                    └── diff 저장 + 요약 로그
```

대표 요청 집합은 대형주·소형주·ETF·거래정지·NXT 지원/미지원·신규상장·데이터 없음 사례를 포함한다.
순위처럼 유니버스가 다른 endpoint는 개별 값 일치율 대신 상위 N 교집합, 순서상관, 누락 이유를 본다.

## 8. 소비자 영향 분석

구현 전 `rg`로 각 `KiwoomRestClient` 메서드와 응답 키의 소비 위치를 목록화한다. 각 필드는 다음 중 하나로
분류한다.

- `required`: 없으면 현재 전략 결과가 달라짐.
- `optional`: 로깅/화면용이며 누락 가능.
- `derived`: KIS 원본 여러 필드에서 계산 가능.
- `unsupported`: KIS에 없고 키움 fallback 필요.
- `unused`: endpoint 응답에 있으나 현재 코드가 읽지 않음.

`required` 필드가 parity를 통과하기 전 해당 endpoint의 provider를 KIS로 바꾸지 않는다.

## 9. 전환 방식

endpoint별 지원 상태를 registry로 관리한다.

```python
ENDPOINT_CAPABILITIES = {
    "stock_info": "kis",
    "daily_chart": "kis",
    "theme_groups": "kiwoom_fallback",
}
```

`MARKET_DATA_PROVIDER=kis`일 때도 registry가 `kiwoom_fallback`인 endpoint만 키움 서버를 호출한다.
KIS 지원 endpoint의 일시 오류는 호출자에게 명시적으로 반환하고 운영자가 provider 전체를 rollback한다.

## 10. 구현 순서

1. 현재 23개 endpoint와 실제 소비 필드 inventory 확정.
2. Batch A 구현, fixture와 shadow comparator 작성.
3. Batch B와 C 구현, 시점·단위 차이를 endpoint 계약에 기록.
4. Batch D 지원 여부 확정 및 명시적 fallback 등록.
5. `KisDataClient`를 `MarketDataClient` factory에 연결.
6. 장중/장후 shadow 실행과 diff 판정.
7. endpoint별 승인 후 `MARKET_DATA_PROVIDER=kis` dry-run.
8. 분석 결과·선정 결과를 키움 실행과 비교한 뒤 기본값 전환 후보로 표시.

## 11. 검증

- adapter fixture: 정상, 빈 결과, pagination, 음수 가격, 0 값, 필드 누락, upstream 오류.
- 각 endpoint가 `kiwoom/:8001` 호환 shape와 타입을 반환하는지 schema test.
- 동일 종목/시점의 가격·거래량·수급 단위 비교.
- chart row 수, 일자 정렬, 중복 candle, 수정주가 여부 확인.
- rank 상위 종목 교집합과 시장 필터 확인.
- `closing_bet`를 주문 전 단계까지 양 provider로 실행해 후보·점수 입력을 비교.
- 키움 fallback 응답에 실제 provider가 표시되고, KIS 오류가 자동 fallback되지 않는지 확인.

## 12. 완료 기준 (DoD)

- [ ] 23개 endpoint가 `kis`, `kiwoom_fallback`, `not_used` 중 하나로 분류됐다.
- [ ] KIS 대상 endpoint의 필수 필드·타입·단위·시점 계약이 문서화됐다.
- [ ] adapter/parser 단위 테스트와 pagination 테스트가 통과한다.
- [ ] shadow diff의 미해결 `missing/type/sign/unit` 오류가 없다.
- [ ] 종가베팅 dry-run의 차이가 설명 가능하고 승인된 diff로 기록된다.
- [ ] 테마 등 미지원 기능은 명시적 키움 fallback이며 키움 코드는 유지된다.
- [ ] `MARKET_DATA_PROVIDER=kiwoom` 회귀와 `kis` 경로가 모두 동작한다.

## 13. 위험과 대응

| 위험 | 대응 |
|---|---|
| 같은 이름의 값이 다른 시점/단위 | endpoint별 계약표와 shadow diff 종류 분리 |
| 빈 값이 0으로 바뀌어 전략 왜곡 | 필수 필드 누락은 실패, nullable 의미 유지 |
| KIS rate limit 초과 | pagination 상한, 요청 묶음, cache, shadow 빈도 제한 |
| KRX/NXT 가격 혼용 | 응답 metadata에 venue/source timestamp 포함 |
| 테마 1:1 대응 부재 | endpoint 단위 키움 fallback 유지 |
| provider 장애가 조용히 감춰짐 | transient error 자동 fallback 금지, 명시적 운영 전환 |
