# Phase 1 — 피처 스냅샷 확장 (NXT 괴리 · 섹터 상대치 · 시장 스냅샷)

> 목표: 가설(F1~F4)이 "볼 수 있는 것"을 넓힌다. **기록하지 않은 피처는 영원히 검증할 수 없다.**
> 이 단계는 매매 행위에 영향 0 — 순수 관측·기록 레이어.

## 1. 배경

`daily_stock_report` 는 이미 수급·차트·뉴스 팩터를 원자 컬럼으로 저장하지만, 관측이
**15:00 KRX 시점에서 멈춘다**. NXT 도입 후 15:30~20:00 애프터마켓은 가격 발견이 진행되는
관측 창인데(F3 의 핵심), 현재는 `gap_check --base-nxt`(19:50)가 top-10 의 NXT 가격을
state 파일에만 임시 보관하고 버린다. 또 F2(해외 동조)·F4(후발 확산)를 검증하려면
시장 레벨 스냅샷과 섹터 상대치가 필요하다.

## 2. 스키마 변경

### 2-1. `daily_stock_report` 컬럼 추가 (종목 단위 피처)

마이그레이션: `jongalab/sql/5. migrate_edge_features.sql` + 정본 `2. create_table.sql` 동기 갱신.

```sql
ALTER TABLE daily_stock_report
  -- 19:50 NXT 스냅샷 (F3 NXT 괴리형의 눈). 수집: gap_check --base-nxt 확장
  ADD COLUMN krx_close_price INT DEFAULT NULL COMMENT '15:30 확정 종가(19:50 수집 — current_price 는 14시대 장중가라 별도 저장)',
  ADD COLUMN nxt_price_1950 INT DEFAULT NULL COMMENT '19:50 NXT 현재가 (미상장/무거래 NULL)',
  ADD COLUMN nxt_gap_pct FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가 → 19:50 NXT 괴리율(%)',
  ADD COLUMN nxt_after_value BIGINT DEFAULT NULL COMMENT 'NXT 애프터 누적 거래대금(원). API 필드 확인 후, 불가 시 NULL 유지',
  ADD COLUMN nxt_listed TINYINT(1) DEFAULT NULL COMMENT '19:50 NXT 조회 성공 여부(NXT 상장 판별)',
  -- 섹터 상대치 (F4 후발 확산형의 눈). 수집: closing_bet 저장 시점 파생(계산만, API 호출 없음)
  ADD COLUMN sector_rel_ret FLOAT DEFAULT NULL COMMENT '당일 등락률 − 유니버스 내 동일 sector 평균 등락률(%p)',
  ADD COLUMN sector_leader_chg FLOAT DEFAULT NULL COMMENT '유니버스 내 동일 sector 최고 등락률(%) — 후발주 판정 분모';
```

설계 노트:
- **krx_close_price 를 따로 두는 이유**: `current_price` 는 closing_bet 실행 시각(13~15시)의
  장중가라 확정 종가가 아니다. NXT 괴리의 분모는 확정 종가여야 하므로 19:50 수집 시
  KRX 현재가(장 마감 후 = 확정 종가)를 같이 저장한다. 종목당 API 2콜(KRX + NXT).
- **sector_rel_ret 을 저장 시점에 파생하는 이유**: predicate 평가기를 행 단위(row-local)로
  단순하게 유지하기 위해서다. 교차 행 계산(섹터 평균·대장주 등락)을 조회 시점마다 하면
  평가기가 복잡해지고 시점 재현이 안 된다. 스냅샷에 구워 넣으면 rule 은 단순 비교만 하면 된다.
- `nxt_after_value`: 키움 `ka10001`(`{code}_NX`) 응답에 거래대금 필드가 있는지 **구현 시 확인**.
  없으면 거래량×현재가 근사 또는 NULL 유지(F3 rule 이 이 컬럼을 조건으로 못 쓸 뿐, 다른 축으로 검증).

### 2-2. `market_snapshot` 테이블 신설 (일 단위 시장 피처)

F2(해외 동조)·레짐 연구용. 종목 행에 중복 저장하지 않고 report_date 로 조인한다.

```sql
CREATE TABLE IF NOT EXISTS market_snapshot (
    snapshot_date  DATE PRIMARY KEY,
    captured_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    kospi_ret      FLOAT DEFAULT NULL,   -- 당일 코스피 등락률(%)
    kosdaq_ret     FLOAT DEFAULT NULL,
    nq_fut_ret     FLOAT DEFAULT NULL,   -- 나스닥100 선물(NQ=F) 등락률 — 19:50 시점
    spx_ret        FLOAT DEFAULT NULL,   -- S&P500 전일 종가 등락률
    sox_ret        FLOAT DEFAULT NULL,   -- 필라델피아 반도체(^SOX) 전일 등락률
    vix            FLOAT DEFAULT NULL,
    usdkrw_ret     FLOAT DEFAULT NULL,
    k200f_day_ret  FLOAT DEFAULT NULL,   -- 코스피200 주간선물 등락률(장 마감 기준)
    k200f_night_ret FLOAT DEFAULT NULL   -- 야간선물 등락률(19:50 시점, kis_night_future)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 3. 코드 변경

| 파일 | 변경 | 비고 |
|---|---|---|
| `workers/closing_bet.py` | `_save_phase2_reports` 에서 `sector_rel_ret`·`sector_leader_chg` 파생 계산 후 reports dict 에 추가 | 유니버스 in-memory 계산, API 콜 없음 |
| `workers/gap_check.py` | `run_base("nxt")`(19:50) 확장: ① 대상을 top-10 → **당일 유니버스 전체**(`include_unselected=True`)로 ② KRX+NXT 현재가 조회 ③ state 파일 저장(기존, 갭 체크용)에 더해 `daily_stock_report` 에 `krx_close_price`·`nxt_price_1950`·`nxt_gap_pct`·`nxt_after_value`·`nxt_listed` UPDATE | 기존 top-10 갭 체크 동작 불변. `market_snapshot` 도 여기서 1행 upsert |
| `core/repository/stock_report.py` | `save_nxt_snapshot(report_date, rows)` 추가 | UPDATE only, upsert 아님(리포트 행이 이미 존재) |
| `core/repository/market_snapshot.py` | 신규 — `save_market_snapshot(row)` / `get_market_snapshots(dates)` | repository 패턴 준수 |
| `core/market_data.py` | `^SOX` 심볼 추가 + `fetch_edge_market_snapshot()` 헬퍼(NQ·SPX·SOX·VIX·환율·K200 선물을 한 번에) | 기존 표시용 함수 재사용 |

### 수집 타이밍과 부하

- 19:50 실행, 유니버스 40~70종목 × 2콜(KRX/NXT) × 0.3s sleep ≈ **30~60초**. NXT 매수 창(19:30
  signal_executor)과 겹치지 않고, `--base-nxt` 크론(19:50)을 그대로 쓰므로 신규 크론 불필요.
- 조회 실패 종목은 NULL 유지(그날 그 종목만 F3 평가 제외) — 파이프라인은 계속 진행.

## 4. 검증

1. `py_compile` 통과 (gap_check·closing_bet·repository 2종·market_data).
2. 마이그레이션을 DB 콘솔로 적용 후, closing_bet 단발 실행 → `sector_rel_ret` 채워짐 확인
   (`/db` 스킬: `SELECT sector, change_pct, sector_rel_ret, sector_leader_chg FROM daily_stock_report WHERE report_date=CURDATE() LIMIT 20`).
3. 19:50 이후 `gap_check --base-nxt` 단발 실행 → `nxt_*`·`krx_close_price` 채워짐 + `market_snapshot` 1행 확인.
4. 다음날 08:03/09:03 갭 체크가 종전과 동일하게 top-10 갭을 확정하는지 확인(회귀 없음).

## 5. 완료 기준 (DoD)

- [ ] 유니버스 전 종목에 19:50 NXT 스냅샷·섹터 상대치가 매 거래일 자동 축적된다.
- [ ] `market_snapshot` 이 매 거래일 1행씩 쌓인다.
- [ ] 기존 갭 체크·매매 흐름에 회귀가 없다.
- [ ] `jongalab/README.md` 워커 표·도메인 흐름 갱신.

## 6. 리스크

- **kiwoom 데이터 서버 부하**: 19:50 에 콜 수 증가. 0.3s sleep 유지로 rate limit 안전권.
  실패 시 개별 NULL — 치명 경로 아님.
- **NXT 거래대금 필드 부재 가능성**: 확인 후 없으면 근사/보류(위 2-1 노트). F3 는 괴리율+
  섹터 동조만으로도 1차 검증 가능.
