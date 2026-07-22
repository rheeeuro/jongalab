# Phase 1 — KIS provider 기반과 데이터 서버 분리

## 1. 목표

KIS 인증·REST 호출·토큰 저장의 소유권을 명확히 하고, 기존 `kiwoom/:8001`과 나란히 실행되는
조회 전용 `kis/:8003`을 만든다. 이 단계에서는 운영 데이터나 실주문 공급자를 바꾸지 않는다.

완료 상태는 다음과 같다.

- `kis/`가 독립 FastAPI 서브프로젝트로 기동된다.
- 토큰 발급·저장·갱신 주체가 하나로 정리된다.
- `jongalab`과 `trading`은 provider factory를 통해 KIS/키움을 선택할 준비가 된다.
- 기본 설정은 계속 키움이며 KIS 장애가 기존 운영에 영향을 주지 않는다.

## 2. 재사용할 코드

| 기존 코드 | 재사용 내용 | 처리 |
|---|---|---|
| `jongalab/core/kis_client.py` | 토큰, approval key, REST session, 숫자 파싱 | `kis/core/`로 일반화 후 기존 import 호환 유지 |
| `jongalab/core/repository/kis_token.py` | 토큰 upsert/read 계약 | 새 `kis` DB repository로 이전, 구 구현은 legacy로 보존 |
| `jongalab/workers/kis_token_refresh.py` | 일일 갱신 패턴 | 새 워커가 소유권을 넘겨받은 뒤 구 워커 비활성화 |
| `kiwoom/core/{config,db,logging_setup}.py` | 독립 서버 구조 | KIS 설정 키만 가진 최소 복제 |
| `kiwoom/api.py` | 내부 데이터 서버 route/health 패턴 | endpoint shape의 기준으로 재사용 |

기존 `jongalab.kis_token` 테이블은 즉시 삭제하지 않는다. 전환 기간에는 읽기 전용 legacy로 두고,
새로운 토큰 쓰기는 `kis` 서비스 하나만 수행한다.

## 3. 디렉터리와 책임

```text
kis/
├── README.md
├── pyproject.toml
├── api.py
├── core/
│   ├── config.py
│   ├── db.py
│   ├── logging_setup.py
│   ├── kis_api/
│   │   ├── __init__.py
│   │   └── base.py              # 인증 헤더, REST 호출, pagination, 오류 변환
│   └── repository/
│       └── kis_token.py
├── workers/
│   └── kis_token_refresh.py
└── sql/
    ├── 1. create_database.sql
    └── 2. create_table.sql
```

`kis`는 데이터 조회 전용 서버다. 주문·계좌 endpoint는 외부에 노출하지 않고 `trading` 내부의 broker
adapter가 KIS에 직접 호출한다. 이렇게 해야 분석 서비스와 자금 경로의 권한을 분리할 수 있다.

## 4. 설정 계약

`.env` 값은 구현자가 직접 작성하지 않는다. `core/config.py`에 다음 이름만 추가하고 배포 환경에서 주입한다.

| 설정 | 사용 주체 | 설명 |
|---|---|---|
| `KIS_APP_KEY` / `KIS_APP_SECRET` | kis, trading | Open API 인증 |
| `KIS_ACCOUNT_NO` | trading | 계좌번호 8자리 |
| `KIS_ACCOUNT_PRODUCT_CODE` | trading | 상품코드 2자리 |
| `KIS_HTS_ID` | trading WS | 주문·체결통보 구독 키 |
| `KIS_DB_NAME` | kis, trading | KIS 토큰 DB, 기본 논리명 `kis` |
| `KIS_DATA_BASE_URL` | jongalab | 내부 조회 서버, `http://127.0.0.1:8003` |
| `MARKET_DATA_PROVIDER` | jongalab | `kiwoom` 또는 `kis` |
| `BROKER_PROVIDER` | trading | `kiwoom` 또는 `kis` |
| `KIS_ENV` | kis, trading | `paper` 또는 `live` |

앱키·시크릿·토큰과 AES key/IV는 로그 구조화 필드에도 넣지 않는다. 계좌번호는 마지막 일부만 표시한다.

## 5. 토큰 소유권과 갱신

### 5.1 정본 테이블

`kis/sql/2. create_table.sql`에 현재 토큰 계약을 옮긴다.

```sql
CREATE TABLE kis_token (
    token_type      VARCHAR(20) NOT NULL PRIMARY KEY,
    access_token    TEXT NOT NULL,
    expires_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
);
```

`token_type`은 최소 `live`, `paper`를 구분한다. approval key는 수명이 짧고 WS 연결 시 발급하므로 DB에
장기 저장하지 않는다.

### 5.2 갱신 규칙

1. `kis_token_refresh.py`만 주기적으로 토큰을 발급하고 DB에 쓴다.
2. API와 trading은 유효 토큰을 DB에서 읽고, 만료 임박 시 process-local lock 안에서 한 번만 갱신한다.
3. 401/토큰 만료 응답은 한 번 재발급 후 원 요청을 한 번만 재시도한다.
4. 여러 프로세스가 동시에 토큰 발급하지 않도록 DB advisory lock 또는 named lock을 사용한다.
5. 새 저장소가 안정화되기 전까지 기존 테이블을 읽는 compatibility fallback은 허용하되 쓰지는 않는다.

## 6. 공통 REST client 계약

`kis/core/kis_api/base.py`는 다음만 책임진다.

- 실전/모의 base URL 선택.
- access token과 `appkey`, `appsecret`, `tr_id`, `custtype` 헤더 구성.
- GET/POST, connect/read timeout, 재시도 가능한 조회 요청의 제한적 backoff.
- 응답의 `rt_cd`, `msg_cd`, `msg1` 확인과 typed exception 변환.
- `tr_cont`, context key를 이용한 연속조회 iterator.
- hashkey가 필요한 POST 요청의 생성.
- 원본 응답의 민감 정보 제거 후 debug logging.

주문 요청은 자동 재시도하지 않는다. 네트워크 timeout 뒤 주문 접수 여부가 불명확하면 주문조회로 먼저
확인하고, idempotency 판단 없이 같은 주문을 재전송하지 않는다.

## 7. 내부 health API

`GET /health` 응답은 다음 shape를 고정한다.

```json
{
  "status": "ok",
  "provider": "kis",
  "environment": "paper",
  "token_expires_at": "2026-07-23T06:00:00+09:00",
  "upstream_reachable": true
}
```

health 호출은 토큰 원문이나 계좌를 반환하지 않는다. upstream 확인은 저비용 endpoint를 사용하고,
실패 시 HTTP 503과 정규화된 오류 코드를 반환한다.

## 8. provider factory

### jongalab

`jongalab/core/market_data_client.py`에 현재 `KiwoomRestClient`의 공개 조회 메서드를 표현하는 Protocol과
factory를 둔다.

```python
class MarketDataClient(Protocol):
    def get_stock_info(self, stk_cd: str) -> dict: ...
    def get_daily_chart(self, stk_cd: str, **kwargs) -> dict: ...
    # 현재 소비되는 전체 메서드

def create_market_data_client(settings) -> MarketDataClient: ...
```

- `kiwoom`: 기존 `KiwoomRestClient` 객체를 그대로 반환한다.
- `kis`: `KisDataClient`가 `kis/:8003`을 호출한다.
- 잘못된 값은 시작 시 즉시 실패시키고 자동 fallback하지 않는다.

`closing_bet.py`는 factory 결과를 `AnalysisEngine`에 전달한다. 따라서 민감 파일인
`jongalab/core/trading_engine.py`는 변경하지 않는다.

### trading

broker Protocol과 실제 KIS 구현은 Phase 3에서 추가한다. 이 단계에서는 `BROKER_PROVIDER` 검증과 factory
자리만 만들고 기존 키움 객체를 반환한다.

## 9. PM2와 운영 등록

`ecosystem.config.js`에 다음 앱을 추가한다.

- `kis-api`: `127.0.0.1:8003` FastAPI 상시 실행.
- `kis-token-refresh`: 토큰 일일 갱신 cron.

새 갱신 워커가 실제 쓰기를 시작한 뒤 기존 `jongalab-kis-token-refresh`가 있다면 중복 실행을 비활성화한다.
키움 앱은 변경하지 않는다.

## 10. 구현 순서

1. `kis/` 프로젝트·설정·DB·repository 생성.
2. 기존 KIS client에서 공통 인증/REST 코드를 이동하고 호환 import 제공.
3. 토큰 refresh를 새 프로젝트로 이전하고 single-writer lock 적용.
4. `/health`와 PM2 앱 추가.
5. `MarketDataClient` Protocol/factory와 `KisDataClient` skeleton 생성.
6. 기존 KIS 지수·선물 호출이 새 기반에서도 동일하게 동작하도록 import 경로 정리.
7. README와 운영 명령 동기화.

## 11. 검증

- 토큰이 유효할 때 재발급 없이 재사용되는지 확인.
- 만료 임박, 401, 동시 요청에서 토큰이 한 번만 갱신되는지 단위 테스트.
- paper/live가 서로 다른 token row와 base URL을 사용하는지 확인.
- `kis-api` 기동 후 `/health` 200 및 민감 정보 미노출 확인.
- `MARKET_DATA_PROVIDER=kiwoom`에서 기존 종가베팅 dry-run 결과가 바뀌지 않는지 확인.
- KIS 장애 상태에서도 `kiwoom/:8001`과 키움 provider가 정상 동작하는지 확인.

## 12. 완료 기준 (DoD)

- [ ] `kis/:8003`과 토큰 refresh가 독립 실행된다.
- [ ] 토큰 writer가 하나뿐이며 legacy 토큰은 삭제되지 않았다.
- [ ] provider 설정 오타가 시작 시 실패한다.
- [ ] 기존 KIS 지수·선물 기능과 키움 기능의 회귀가 없다.
- [ ] 앱키·토큰·계좌 전체번호가 로그/health/예외에 노출되지 않는다.
- [ ] `kis/README.md`, `jongalab/README.md`, 루트 운영 문서가 실제 구조와 일치한다.

## 13. 위험과 대응

| 위험 | 대응 |
|---|---|
| 여러 프로세스의 토큰 동시 발급 | DB lock + single writer + 만료 임박 갱신 |
| 기존 KIS 코드 import 파손 | compatibility module을 먼저 제공하고 단계적으로 이동 |
| 내부/외부 base URL 혼동 | `KIS_DATA_BASE_URL`과 upstream 설정 이름 분리 |
| KIS 장애가 키움 운영까지 전파 | 프로세스·DB·provider 설정 분리, 초기 기본값 키움 |
| 주문 권한이 조회 서버에 노출 | `kis/:8003`은 조회 endpoint만 공개 |
