# Phase 2 — 결과 라벨 다중화 (익일 고저종 + 08:03 NXT 전 유니버스)

> 목표: "청산을 언제 하느냐"가 실측 최대 레버(08:03 vs 08:05 = +0.35%)인데, 현재 결과 라벨은
> `next_open_ret`(익일 시가) 하나뿐이라 rule 별 최적 청산창을 비교할 수 없다.
> 라벨을 1개 → 5개로 늘려 **하루의 표본 정보량을 다중화**한다(물리 제약 ④의 우회).

## 1. 현재 라벨 현황

| 라벨 | 커버리지 | 수집 |
|---|---|---|
| `next_open_ret` (종가→익일 시가) | 유니버스 전체 ✅ | outcome_backfill, 일봉 백필 |
| `gap_nxt_pct` (19:50→08:03 NXT) | **top-10 만** | gap_check 실시간 |
| `gap_krx_pct` (15:20→09:03 KRX) | **top-10 만** | gap_check 실시간 |

문제: 비선정 후보(selected=0)의 08:03 NXT 결과가 없어서, "NXT 프리마켓 청산이 유리한
rule 인가"를 유니버스 반사실로 검증할 수 없다.

## 2. 스키마 변경

마이그레이션: `jongalab/sql/6. migrate_outcome_labels.sql` + 정본 동기 갱신.

```sql
ALTER TABLE daily_stock_report
  -- 일봉 백필 라벨 (outcome_backfill 확장 — 같은 일봉 1회 조회에서 공짜로 나옴)
  ADD COLUMN next_high_ret  FLOAT DEFAULT NULL COMMENT '종가→익일 고가 등락률(%) — 장중 최대 실현 가능치',
  ADD COLUMN next_low_ret   FLOAT DEFAULT NULL COMMENT '종가→익일 저가 등락률(%) — 꼬리 리스크(스톱 관통 측정)',
  ADD COLUMN next_close_ret FLOAT DEFAULT NULL COMMENT '종가→익일 종가 등락률(%) — 홀드 시나리오',
  -- 실시간 수집 라벨 (gap_check 확장)
  ADD COLUMN nxt_open_price INT DEFAULT NULL COMMENT '익일 08:06 NXT 가격 (유니버스 전체)',
  ADD COLUMN nxt_open_ret   FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가(krx_close_price)→익일 08:06 NXT 등락률(%)';
```

설계 노트:
- **앵커 통일**: 연구 라벨의 분모는 전부 **KRX 확정 종가**(Phase 1 의 `krx_close_price`,
  없으면 일봉 종가)로 통일한다. 실집행 창(19:50 NXT 기준 gap_nxt_pct)과 앵커가 다르지만,
  rule 간 공정 비교에는 통일 앵커가 필요하다. 기존 `gap_*` 컬럼(실매매 창 재현)은 그대로 존치
  — 용도가 다르다(집행 검증 vs 엣지 연구).
- **08:06 인 이유**: 08:03 은 실매매 청산(settle --venue nxt)과 gap_check top-10 이 도는
  시각이다. 유니버스 전체(~60콜) 조회를 같은 시각에 얹으면 kiwoom 서버 부하가 실매매 경로와
  경합한다. 연구 라벨은 3분 늦어도 되므로 **08:06 별도 패스**로 분리한다(실측상 08:03 이후
  프리마켓이 식는 것도 라벨에 반영됨 — 보수적 라벨이라 오히려 안전).
- `next_low_ret` 은 veto·리스크 연구의 핵심이다: "이 rule 의 갭다운 꼬리가 하드 손절을
  얼마나 관통하는가"를 rule 승격 심사에서 함께 본다.

## 3. 코드 변경

| 파일 | 변경 |
|---|---|
| `workers/outcome_backfill.py` | `_overnight_ret` → `_overnight_rets` 로 확장: 같은 일봉에서 익일 (시가·고가·저가·종가) 4개 등락률 반환. `save_next_open_ret` 호출부에 3개 라벨 추가. **추가 API 콜 0** (일봉 캐시 그대로) |
| `workers/gap_check.py` | 신규 모드 `--label-nxt`(08:06): 전일 유니버스 전체를 `include_unselected=True` 로 로드 → NXT 상장 종목(`nxt_listed=1`)만 NXT 현재가 조회 → `nxt_open_price`·`nxt_open_ret` UPDATE. 기존 `--check-nxt`(08:03, top-10)와 완전 분리 |
| `core/repository/stock_report.py` | `get_rows_missing_outcome` 반환에 라벨 컬럼 추가, `save_next_open_ret` → `save_outcome_labels` 확장(하위호환), `save_nxt_open_labels` 추가 |
| `ecosystem.config.js` | `jongalab-gap-label-nxt` 크론 추가: `6 8 * * 1-5` (자동 배포 훅이 신규 앱 자동 등록) |

일봉 고저 캔들 필드: `ka10081` 응답의 `high_pric`/`low_pric` — outcome_backfill 의
`_build_ohlc_by_date` 를 (시가,종가) → (시가,고가,저가,종가) 튜플로 확장.
`±35%` 아티팩트 가드(`_SANE_RET_PCT`)는 4개 라벨에 동일 적용.

## 4. 백필 범위

- 신규 라벨 3종(next_high/low/close)은 **과거 유니버스 전체에 소급 백필 가능**(일봉에 다 있음).
  outcome_backfill 은 이미 "라벨 비면 재시도" 구조라, 마이그레이션 직후 첫 실행이 자동 소급한다.
  단 `get_dates_missing_outcome` 의 대상 판정을 `next_open_ret IS NULL` → "라벨 4종 중 NULL 존재"로
  갱신해야 한다.
- `nxt_open_ret` 은 실시간 수집이라 소급 불가 — 배포일부터 축적(그래서 조기 배포가 중요).

## 5. 검증

1. `py_compile` 통과.
2. outcome_backfill 단발 실행 → 과거 행에 `next_high_ret/next_low_ret/next_close_ret` 소급 확인,
   스팟 체크: 임의 3종목의 값을 차트와 대조.
3. 익일 08:06 이후 `--label-nxt` 단발 실행 → NXT 상장 종목에 `nxt_open_ret` 채워짐,
   NXT 미상장 종목은 NULL 유지 확인.
4. 기존 gap_check 4개 모드·outcome 백필의 회귀 없음 확인.

## 6. 완료 기준 (DoD)

- [ ] 유니버스 전 종목이 매 거래일 결과 라벨 5종을 갖는다(NXT 미상장은 4종).
- [ ] 과거 데이터에 고저종 라벨이 소급 백필됐다.
- [ ] 실매매 경로(08:03 settle·gap_check)와 시간·부하가 분리되어 있다.
- [ ] `jongalab/README.md` 갱신.

## 7. 리스크

- 08:06 조회 실패 → 그날 라벨 NULL(연구 표본만 감소, 매매 무영향). 워커 실패는 로그로 관측.
- 일봉 고저에 장중 VI·단일가 왜곡이 섞일 수 있음 — next_high/low 는 "이론상 최대/최악"으로만
  해석하고, 청산창 실측은 nxt_open_ret(체결 가능 시각 스냅샷)을 우선한다. 문서·컬럼 코멘트에 명시.
