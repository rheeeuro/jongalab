# kiwoom — 키움 데이터 전용 API 서버

키움증권 REST API 에서 시세·수급·차트·테마·순위 데이터를 조회하는 **읽기 전용** 서버
(FastAPI, `:8001`). jongalab/trading 메인 도메인이 직접 키움을 부르지 않고, 이 서버를 통해서만
데이터를 받아 간다(jongalab 은 `core.kiwoom_client.KiwoomRestClient` 로 호출).

> **불변식: 데이터 조회 전용.** 주문(`ordr`)·계좌(`acnt`) TR/엔드포인트는 **절대 노출하지 않는다.**
> 주문 권한은 `trading/` 도메인의 `kiwoom_order_client` 만 보유한다.
>
> 이 README 는 주요 로직·코드 구조의 소스 오브 트루스다. 엔드포인트나 클라이언트 로직을 바꾸면
> **이 파일도 함께 갱신**한다. 작업 규칙은 루트 [`AGENTS.md`](../AGENTS.md) 를 따른다.

---

## 코드 구조

```
kiwoom/
├── api.py                       # FastAPI — 데이터 조회 엔드포인트 22종 + /, /health
├── core/
│   ├── config.py                # .env 로딩, kiwoom DB 설정 (DB키만 최소 복제)
│   ├── db.py                    # 컨텍스트 매니저 get_db()
│   ├── logging_setup.py         # 로그 설정 (httpx 로그 억제)
│   ├── kiwoom_api/              # 키움 REST 클라이언트 (TR별 Mixin 조립)
│   │   ├── _base.py             # KiwoomConfig, _BaseClient: 인증·_post·연속조회
│   │   ├── stock_info.py        # ka10001/ka10100/ka10002/ka10059/ka90004/ka10099/ka10013
│   │   ├── market.py            # ka10004/ka10063/ka90008/ka90013/ka10087/ka10066/ka10046/ka10047 (호가·시세·프로그램·시간외)
│   │   ├── rank.py              # ka10032/ka90009/ka10037/ka10035/ka10098 (순위)
│   │   ├── theme.py             # ka90001/ka90002 (테마)
│   │   ├── frgn_inst.py         # ka10131/ka10008/ka10009 (기관·외국인)
│   │   ├── chart.py             # ka10080/ka10081 (분봉·일봉)
│   │   └── short_sale.py        # ka10014/ka20068 (공매도·대차거래)
│   └── repository/
│       └── kiwoom_token.py      # kiwoom_token 테이블 CRUD (get/save/clear, id=1)
├── workers/
│   └── kiwoom_token_refresh.py  # 매일 07:00 토큰 갱신 (PM2 cron)
└── sql/                         # kiwoom DB 스키마 (kiwoom_token 단일행)
```

---

## 핵심 로직

### `core/kiwoom_api/` — 키움 REST 클라이언트
키움 TR 을 도메인별 Mixin 7개로 나눠 `KiwoomRestAPI` 클래스로 조립한다.
- `_base.py` 의 `_BaseClient` 가 공통 인프라를 담당: 토큰 발급/폐기(au10001/au10002),
  `ensure_token()`(DB 토큰 로드 또는 신규 발급, 만료 5분 마진), `_post()`(429 자동 재시도),
  `fetch_all_pages()`(cont-yn/next-key 연속조회).
- 신규 TR 추가 시: 해당 도메인 Mixin 에 메서드를 더하고, `api.py` 에 엔드포인트를 노출한다.
  **주문/계좌 TR 은 추가 금지**(읽기 전용 불변식).

### 토큰 수명주기
토큰은 `kiwoom` DB 의 `kiwoom_token`(id=1 단일행)에 저장된다. 발급/갱신은
`workers/kiwoom_token_refresh.py`(매일 07:00 cron)가 담당하고, 소비자(이 서버의 요청 처리)는
`ensure_token()` 으로 유효 토큰을 읽어 쓴다. trading 도메인은 같은 토큰을 **읽기 전용**으로 공유한다.

---

## 엔드포인트 (api.py, 모두 POST)
| 경로 | TR | 용도 |
|---|---|---|
| `/stock/basic-info` | ka10001 | 주식 기본정보(시총·52주 고저 등) |
| `/stock/detail-info` | ka10100 | 종목정보(업종·시장분류) |
| `/stock/order-book` | ka10004 | 10호가 매도/매수 잔량·호가 스냅샷(연속장 중만 유효 — jongalab 호가 미시구조 피처용) |
| `/stock/broker` | ka10002 | 거래원 상위 5 매도/매수 |
| `/stock/list` | ka10099 | 시장별 상장종목 리스트(코스피/코스닥 code·name) |
| `/stock/intraday-investor` | ka10063 | 종목별 투자자(개인/기관/외국인) |
| `/stock/after-hours-price` | ka10087 | 시간외 단일가 시세·호가 스냅샷(익일 갭 선행지표) |
| `/stock/credit-trend` | ka10013 | 신용융자/대주 일별 추이(잔고율 — 반대매매 리스크) |
| `/stock/short-sale-trend` | ka10014 | 공매도량/비중 일별 추이(기본 최근 30일) |
| `/stock/lending-trend` | ka20068 | 대차잔고 증감 일별 추이(기본 최근 30일) |
| `/stock/execution-strength-daily` | ka10047 | 체결강도 일별 추이(당일·5/20/60일 평균) |
| `/stock/execution-strength-hourly` | ka10046 | 체결강도 당일 시간별 추이(5/20/60분 평균) |
| `/chart/daily` | ka10081 | 일봉 차트 |
| `/chart/minute-pages` | ka10080 | 분봉 차트(연속조회 다건 수집) |
| `/rank/trading-value` | ka10032 | 거래대금 상위 (`mrkt_tp` 000=전체·001=코스피·101=코스닥, `max_pages` 연속조회 — 1페이지 100행. 페이지 수와 무관하게 `trde_prica_upper` 단일 리스트로 반환) |
| `/rank/after-hours-flu` | ka10098 | 시간외 단일가 등락률 순위(시장 전체 스캔) |
| `/market/after-close-investor` | ka10066 | 장마감후 확정 투자자별 순매수(연속조회 병합) |
| `/program-trade/by-stock` | ka90004 | 종목별 프로그램 매매 현황 |
| `/program-trade/daily-trend` | ka90013 | 종목 일별 프로그램 매매 추이 |
| `/program-trade/hourly-trend` | ka90008 | 종목 당일 틱 프로그램 시계열(통합 SOR, 최신→과거, `until_tm` 조기중단·`max_pages`) — jongalab 프로그램 오전/오후 스냅샷용 |
| `/inst-foreign/consecutive` | ka10131 | 기관·외국인 연속 매매 현황 |
| `/theme/groups`, `/theme/stocks` | ka90001/ka90002 | 테마 그룹 / 구성 종목 |

유틸: `GET /`(상태), `GET /health`(DB·토큰 보유 점검).

---

## 기동
```bash
uv run --directory kiwoom uvicorn api:app --host 127.0.0.1 --port 8001
```

## 유지보수
- 변경 전 이 README 로 구조를 파악하고, 변경 후 엔드포인트/TR 표를 갱신한다.
- DB 접근은 `core/repository/*` 만, 비밀키는 `.env` → `core/config.py` 경유.
- 검증: `uv run --directory kiwoom python -m py_compile <file>`, 기동 후 `curl :8001/health`.
