# 07 — exec_leg_ret 전환 적용 및 검증 노트

> 작성: 2026-07-08. 목적은 실험실(rule_evaluator) 채점 라벨을 실제 청산 venue 창에 맞춘
> `exec_leg_ret`로 전환한 변경을 다른 LLM/에이전트가 빠르게 검증할 수 있게 남기는 것이다.

## 1. 요구사항

rule_evaluator가 차트를 보고 다음 기준으로 채점하도록 변경했다.

| venue | 기준가 | 청산가 | 라벨 |
|---|---|---|---|
| NXT | 전일 19:50 NXT 1분봉 첫 체결가 | 익일 08:03 NXT 1분봉 첫 체결가 | `exec_leg_ret`, `exec_leg_venue='NXT'` |
| KRX | 전일 15:20 KRX 1분봉 첫 체결가 | 익일 09:03 KRX 1분봉 첫 체결가 | `exec_leg_ret`, `exec_leg_venue='KRX'` |

중요한 해석:
- 기존 `nxt_open_ret`는 `KRX 확정 종가 → 08:06 NXT`라 이번 요구와 다르다.
- 기존 `gap_nxt_pct`/`gap_krx_pct`는 top-10 중심이라 유니버스 전체 evaluator 기본 라벨로 쓰지 않는다.
- `exec_leg_ret`는 종목별 실제 청산 venue 창을 하나로 접은 evaluator 기본 라벨이다.

## 2. 코드 변경 요약

| 파일 | 변경 내용 |
|---|---|
| `jongalab/core/daily_ohlc.py` | 1분봉 조회/파싱 헬퍼 `build_minute_price_by_time`, 지정 시각 이후 첫 체결가 `first_price_at_or_after`, 다음 거래일 탐색 `first_later_chart_date`, 공통 등락률 가드 `ret_pct` 추가 |
| `jongalab/core/repository/stock_report.py` | `get_dates_missing_exec_leg`, `get_rows_missing_exec_leg`, `save_exec_leg_labels` 추가 |
| `jongalab/workers/outcome_backfill.py` | 기존 일봉 4종 라벨 백필 후 `exec_leg_ret`/`exec_leg_venue` 백필 pass 추가 |
| `jongalab/core/repository/edge_rule.py` | `ALLOWED_EXIT_LABELS`에 `exec_leg_ret` 추가, 신규 rule 기본 `exit_label='exec_leg_ret'` |
| `jongalab/routers/edge_rule.py` | 신규 rule 생성 기본 `exit_label='exec_leg_ret'` |
| `jongalab/routers/stock_report.py` | API 응답 모델에 `exec_leg_ret`, `exec_leg_venue` 추가 |
| `jongalab/frontend/lib/edge.ts` | `exec_leg_ret` 표시 문구 추가 |
| `jongalab/frontend/types/index.ts` | `StockReport` 타입에 `exec_leg_ret`, `exec_leg_venue` 추가 |
| `jongalab/sql/2. create_table.sql` | `daily_stock_report.exec_leg_*`, `edge_rule.exit_label` 기본값 반영 |
| `jongalab/sql/7. migrate_edge_ledger.sql` | 신규 설치/마이그레이션 기본값 `exec_leg_ret` 반영 |
| `jongalab/sql/8. seed_edge_rules.sql` | seed rule의 `exit_label`을 `exec_leg_ret`로 변경 |
| `jongalab/sql/11. migrate_exec_leg_label.sql` | 운영 DB 적용용 migration 추가 |
| `jongalab/tests/test_daily_ohlc.py` | 분봉 헬퍼/날짜 오염 방지/±35% 가드 테스트 추가 |
| `jongalab/README.md` | 워커/라벨/evaluator 흐름 동기화 |

## 3. 백필 범위 제한

처음 구현한 `get_dates_missing_exec_leg()`는 라벨이 비어 있는 모든 과거 날짜를 대상으로 잡을 수 있었다.
하지만 활성 rule은 2026-07-07에 등록됐으므로, evaluator 채점에 필요한 시작일도 2026-07-07이다.

이를 막기 위해 `outcome_backfill.py`에 `_earliest_exec_label_registered_at()`를 추가했다.

- `list_rules(exclude_retired=True)`에서 `exit_label == 'exec_leg_ret'`인 활성 rule의 가장 이른 `registered_at`을 찾는다.
- CLI 인자로 `min_date`를 주지 않으면 그 날짜 이후만 `exec_leg_ret` 백필한다.
- 따라서 일반 cron 실행도 evaluator가 쓰지 않을 과거 분봉을 다시 조회하지 않는다.

## 4. 실제 DB 적용 이력

실제 적용 순서는 다음과 같다.

1. `jongalab/sql/11. migrate_exec_leg_label.sql` 실행
   - 주석 포함 SQL split 문제로 첫 `ALTER TABLE daily_stock_report`가 누락됨
   - `edge_rule.exit_label` 전환은 적용됨: 23행
2. 누락된 `daily_stock_report` 컬럼 추가를 수동 실행
3. 처음 잘못 넓게 시작한 백필 프로세스 중지
4. 2026-07-07 이전에 이미 채워진 `exec_leg_*` 108행을 NULL로 되돌림
5. `workers/outcome_backfill.py 2026-07-07`로 정확히 하루만 백필
6. `workers/rule_evaluator.py` 재실행

## 5. 현재 검증된 DB 상태

2026-07-08 14:01 기준 확인값:

| 항목 | 값 |
|---|---:|
| 2026-07-07 이전 `exec_leg_ret` 채움 | 0 |
| 2026-07-07 `exec_leg_ret` 채움 | 40 / 41 |
| 2026-07-07 NXT 라벨 | 33 |
| 2026-07-07 KRX 라벨 | 7 |
| 활성 rule `exit_label='exec_leg_ret'` | 23 |
| `edge_rule_daily` 생성 날짜 | 2026-07-07 only |
| `edge_rule_daily` 행 수 | 23 |
| `edge_rule_daily.n_matched` 합 | 79 |

1개 미채움은 분봉 양 끝 중 하나가 없어 NULL로 남은 것으로 본다. evaluator는 NULL ret은 평균 계산에서 제외한다.

## 6. 재검증 명령

아래 명령은 루트(`/home/euro/dev/jongalab`)에서 실행한다.

### 6.1 코드 검증

```bash
uv run --directory jongalab python -m py_compile \
  core/daily_ohlc.py \
  core/repository/stock_report.py \
  core/repository/__init__.py \
  workers/outcome_backfill.py \
  core/repository/edge_rule.py \
  routers/edge_rule.py \
  routers/stock_report.py

uv run --directory jongalab --group dev pytest tests/test_daily_ohlc.py

cd jongalab/frontend
npx tsc --noEmit
npm run lint
```

기대 결과:
- `py_compile`: 출력 없음, exit 0
- `pytest tests/test_daily_ohlc.py`: `3 passed`
- `tsc`: 출력 없음, exit 0
- `lint`: exit 0

### 6.2 DB 상태 확인

```bash
uv run --directory jongalab python - <<'PY_DB_CHECK'
from core.db import get_db

with get_db() as (conn, c):
    c.execute("""
        SELECT COUNT(*) total,
               SUM(exec_leg_ret IS NOT NULL) filled,
               SUM(report_date < '2026-07-07' AND exec_leg_ret IS NOT NULL) prefilled
          FROM daily_stock_report
         WHERE report_date <= '2026-07-07'
    """)
    print('labels', c.fetchone())

    c.execute("""
        SELECT exec_leg_venue venue, COUNT(*) n
          FROM daily_stock_report
         WHERE report_date = '2026-07-07'
           AND exec_leg_ret IS NOT NULL
         GROUP BY exec_leg_venue
         ORDER BY exec_leg_venue
    """)
    print('venues', c.fetchall())

    c.execute("""
        SELECT exit_label, COUNT(*) n
          FROM edge_rule
         WHERE status <> 'retired'
         GROUP BY exit_label
    """)
    print('rules', c.fetchall())

    c.execute("""
        SELECT report_date, COUNT(*) n, SUM(n_matched) matched_total
          FROM edge_rule_daily
         GROUP BY report_date
         ORDER BY report_date
    """)
    print('daily', c.fetchall())
PY_DB_CHECK
```

기대 결과 예시:

```text
labels {'total': 672, 'filled': Decimal('40'), 'prefilled': Decimal('0')}
venues [{'venue': 'KRX', 'n': 7}, {'venue': 'NXT', 'n': 33}]
rules [{'exit_label': 'exec_leg_ret', 'n': 23}]
daily [{'report_date': datetime.date(2026, 7, 7), 'n': 23, 'matched_total': Decimal('79')}]
```

## 7. 수동 재실행 절차

정상 재실행은 아래 순서다.

```bash
uv run --directory jongalab python workers/outcome_backfill.py 2026-07-07
uv run --directory jongalab python workers/rule_evaluator.py
```

주의:
- `outcome_backfill.py`에 날짜 인자를 주면 해당 날짜 이후가 대상이다.
- 날짜 인자를 생략하면 `exec_leg_ret`는 활성 rule의 가장 이른 `registered_at` 이후만 자동 대상화한다.
- `edge_rule_daily`는 migration에서 active rule 기준으로 삭제된 뒤 evaluator로 재생성됐다.

## 8. 운영상 주의점

- `exec_leg_ret`는 분봉 기반이라 일봉 라벨보다 API 호출 비용이 크다. 과거 전체 백필을 금지하고 registered_at 이후로 제한한 이유다.
- `nxt_listed`가 0이면 KRX 레그로 계산한다. `nxt_listed`가 NULL인 과거/결측 행은 NXT를 먼저 시도하고 실패 시 KRX로 폴백한다.
- `ret_pct`는 기존 라벨과 같은 `SANE_RET_PCT=35.0` 가드를 쓴다. 초과하면 분할/데이터 아티팩트로 보고 NULL 유지한다.
- `next_low_ret`는 현재 2026-07-07 일부 행에서 없을 수 있어 evaluator 로그의 `worst_low_ret`가 `None`일 수 있다. `exec_leg_ret` 평균 채점과는 별개다.
- 이번 변경은 `trading/` 주문/리스크/집행 로직을 건드리지 않는다. 실험실 채점 라벨과 관측 백필만 바꿨다.

## 9. 확인할 만한 코드 포인트

- `workers/outcome_backfill.py::_earliest_exec_label_registered_at`
- `workers/outcome_backfill.py::_exec_leg_label`
- `core/daily_ohlc.py::first_price_at_or_after`
- `core/repository/edge_rule.py::ALLOWED_EXIT_LABELS`
- `workers/rule_evaluator.py::_score_rule_date`

다른 LLM이 검증할 때 가장 중요한 질문은 두 가지다.

1. `exec_leg_ret`가 2026-07-07 이전에 채워져 있지 않은가?
2. `edge_rule_daily`가 2026-07-07 하루치만 `exec_leg_ret` 기준으로 재생성됐는가?

위 6.2 쿼리가 두 질문을 모두 검증한다.
