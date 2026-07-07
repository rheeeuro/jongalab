# Phase 3 — Edge Ledger (가설 원장 · predicate 평가기 · rule_evaluator 워커)

> 목표: 시스템의 1급 시민을 "오늘의 종목"에서 "가설(rule)"로 바꾸는 심장부.
> 모든 가설은 DB 행으로 존재하고, 매일 자동으로 채점되며, 표본과 성적으로만 승격된다.

## 1. 스키마

마이그레이션: `jongalab/sql/7. migrate_edge_ledger.sql` + 정본 동기 갱신.

```sql
-- 가설 원장. 1행 = 반증가능한 가설 1개.
CREATE TABLE IF NOT EXISTS edge_rule (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(50) NOT NULL UNIQUE,      -- 예: f3_nxt_gap_quality
    family       VARCHAR(20) NOT NULL,             -- f1_news / f2_global / f3_nxt / f4_laggard / control / veto
    description  VARCHAR(500) NOT NULL,            -- 인과 근거 필수: "누가 왜 내일 아침 사는가"
    predicate    JSON NOT NULL,                    -- 조건 목록(아래 DSL), AND 결합
    exit_label   VARCHAR(30) NOT NULL DEFAULT 'next_open_ret',  -- 채점에 쓸 결과 라벨 컬럼
    status       VARCHAR(10) NOT NULL DEFAULT 'candidate',      -- candidate / live / retired
    min_sample   INT NOT NULL DEFAULT 40,          -- 승격 심사 최소 표본(매칭 종목-일)
    registered_at DATE NOT NULL,                   -- ★ 사전 등록일 — 이 날짜 이후 표본만 승격 판정에 사용
    stats        JSON DEFAULT NULL,                -- evaluator 갱신 캐시(n, mean_net, win_rate, ci_low, max_dd, updated_through)
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    promoted_at  TIMESTAMP NULL DEFAULT NULL,
    retired_at   TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 일별 평가 결과 (스코어보드 시계열 + 감사 추적)
CREATE TABLE IF NOT EXISTS edge_rule_daily (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id      INT NOT NULL,
    report_date  DATE NOT NULL,
    n_matched    INT NOT NULL DEFAULT 0,
    mean_net_ret FLOAT DEFAULT NULL,               -- 매칭 종목 평균 (exit_label − EDGE_COST_PCT)
    matched      JSON DEFAULT NULL,                -- [{code, name, ret}] 감사·복기용
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_rule_date (rule_id, report_date),
    INDEX idx_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 2. Predicate DSL — 의도적으로 단순하게

조건 목록의 AND 결합. OR·중첩은 지원하지 않는다 — **OR 가 필요하면 rule 을 쪼갠다**
(가설은 원자적이어야 귀속이 된다). 교차 행 계산이 필요한 조건은 Phase 1 처럼
스냅샷 시점에 파생 컬럼으로 구워 predicate 를 행 단위로 유지한다.

```json
[
  {"col": "nxt_gap_pct",   "op": "between", "value": [1.0, 6.0]},
  {"col": "sector_rel_ret","op": ">=",      "value": 0},
  {"col": "news_first_today", "op": "==",   "value": 1},
  {"col": "market.nq_fut_ret", "op": ">=",  "value": -0.3}
]
```

- `op`: `==` `!=` `>=` `<=` `between` `in` `not_null` (7종으로 시작, 필요 시 추가)
- `col` 에 `market.` 접두사 → `market_snapshot`(report_date 조인)의 컬럼 참조 (F2 용)
- NULL 처리: 조건 대상 컬럼이 NULL 인 행은 **매칭 실패**로 처리(보수적 — NULL 을 통과시키면
  결측이 많은 날 rule 이 오염된다)

평가기는 `core/edge_predicate.py` (신규, ~100줄 순수 함수):
`evaluate(predicate: list, row: dict, market: dict) -> bool`.
**DB·네트워크 무의존 순수 로직 → `jongalab/tests/test_edge_predicate.py` 단위 테스트 필수**
(op 별 정상/경계/NULL/미지원 op 에러).

## 3. rule_evaluator 워커

`workers/rule_evaluator.py`, cron `40 9 * * 1-5` (outcome_backfill 09:30 이후).

```
1. 활성 rule 로드 (status != 'retired')
2. 채점 대상 날짜: edge_rule_daily 에 없는 report_date × 결과 라벨이 채워진 날짜 (자동 캐치업)
3. 날짜별로 유니버스 로드(include_unselected=True) + market_snapshot 조인
4. rule × 날짜: predicate 매칭 → exit_label 값 수집 → mean_net = mean(label) − EDGE_COST_PCT
   → edge_rule_daily upsert
5. rule 별 누적 통계 재계산 (registered_at 이후 표본만):
   n, mean_net, win_rate, std, ci_low = mean_net − 1.64·std/√n (단측 95%),
   worst = min(next_low_ret 분포)  ← 꼬리 심사용
   → edge_rule.stats 캐시 갱신
6. 상태 전이 알림 (전이는 알림만, 실제 변경은 수동 승인):
   - candidate: n ≥ min_sample AND ci_low > 0        → "승격 후보" 텔레그램
   - live:      최근 30표본 mean_net < 0 (n≥20)       → "강등 검토" 텔레그램
7. [건강지표] 로깅: rule 별 n/mean_net/ci_low 요약 (weight_tuner 관례를 따름)
```

비용 상수: `.env` → `core/config.py` 에 `EDGE_COST_PCT` (기본 0.25 = 세금 0.15 + 수수료 + 슬리피지
보수 추정). trading `fill` 실측치로 분기별 보정하고 보정 이력을 이 문서에 기록한다.

## 4. 승격/강등 절차 (수동 게이트 — weight_tuning 승인 패턴 재사용)

| 전이 | 조건 | 실행 주체 |
|---|---|---|
| candidate → live | n≥min_sample, ci_low>0, **대조군(control_legacy_top10) mean_net 이상**, next_low_ret 꼬리가 하드 손절 정책과 양립, 사용자 승인 | 관리자 API |
| live → retired | 성적 붕괴 알림 후 사용자 판단 (또는 즉시 수동) | 관리자 API |
| veto family 예외 | 감액 전용(reduce-only)이라 ci 검증 없이 live 가능 — 단 적용 내역은 edge_rule_daily 로 동일 기록 | 관리자 API |

- **승격 판정에 registered_at 이전 표본을 절대 쓰지 않는다** (사전 등록 원칙 — README §5).
  과거 소급 라벨(Phase 2)로 "참고 백테스트"는 볼 수 있으나 stats 와 분리 표기한다.
- 다중 가설 보정: 동시 심사 rule 이 많아질수록 우연 통과가 늘어난다. 운영 완화책으로
  live 승격은 **월 최대 2개**로 제한하고, 승격 후 첫 2주는 시드 배분 가중 0.5 로 시작(Phase 4).

## 5. API (routers/edge_rule.py — 신규, admin 인증은 기존 admin 라우터 패턴)

| 엔드포인트 | 용도 |
|---|---|
| `GET /api/edge-rules` | 목록 + stats (공개 — 대시보드 표시) |
| `GET /api/edge-rules/{id}/daily?days=60` | 일별 성적 시계열 (스코어보드 차트) |
| `POST /api/edge-rules` (admin) | 신규 rule 등록 (predicate 검증 포함) |
| `POST /api/edge-rules/{id}/promote` (admin) | candidate→live (조건 미충족 시 409 + 사유, force 불가) |
| `POST /api/edge-rules/{id}/retire` (admin) | live/candidate→retired |

`api.py` 에 `include_router` 등록. repository 는 `core/repository/edge_rule.py`.

## 6. 검증

1. `test_edge_predicate.py` pytest 통과 (op 7종 × 정상/NULL/경계).
2. rule_evaluator 단발 실행 → 시드 rule(04 문서)의 edge_rule_daily 생성 확인,
   수동 SQL 로 1개 rule 의 mean_net 을 교차 계산해 일치 확인.
3. API 기동 후 `curl` 로 5개 엔드포인트 status·shape 확인 (promote 는 조건 미충족 409 확인).
4. 텔레그램 알림 형식 확인 (승격 후보 mock).

## 7. 완료 기준 (DoD)

- [ ] rule 등록→매일 자동 채점→누적 통계→승격 알림의 루프가 무인으로 돈다.
- [ ] 승격은 API 로만, 조건 미충족 승격은 코드가 거부한다.
- [ ] predicate 평가기 단위 테스트가 있다.
- [ ] `jongalab/README.md` 워커·라우터·흐름 갱신.

## 8. 리스크

- **과적합(다중 가설)**: 사전 등록 원칙 + 월 승격 상한 + 대조군 우위 요구로 3중 방어.
  그래도 우연 통과는 0이 안 되므로 live 이후에도 성적 붕괴 감시(6번 알림)가 상시 돈다.
- **평가기 버그 = 조용한 오판**: 순수 함수 분리 + 단위 테스트 + edge_rule_daily.matched 에
  감사용 원본을 남겨 언제든 수동 재검산 가능하게 한다.
