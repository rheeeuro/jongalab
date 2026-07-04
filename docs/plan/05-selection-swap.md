# Phase 4 — 선정 레이어 전환 (live rule 합집합 선정 + rule_id 관통)

> ⚠️ **데이터 게이트가 있는 단계.** 착수 조건: ①어느 candidate 가 n≥min_sample & ci_low>0
> ②대조군(control_legacy_top10) 대비 mean_net 우위 ③꼬리(next_low_ret 분포)가 하드 손절
> 정책과 양립 ④사용자 명시 승인. 예상 시점 8월 중순 이후(표본 축적 4~8주).

## 1. 전환 설계 — 3단 모드 스위치

`closing_bet.py` 에 선정 모드를 둔다 (`.env` → `EDGE_SELECTION_MODE`, 기본 `legacy`):

| 모드 | selected 판정 | 용도 |
|---|---|---|
| `legacy` | 현행: 점수 rank_no ≤ TRADED_TOP_N | 기본값. Phase 1~3 기간 내내 유지 |
| `hybrid` | live rule 매칭 종목 **우선** 배치 + 잔여 슬롯을 점수순으로 채움 (총 상한 TRADED_TOP_N) | 전환 1단계 — 최악의 경우에도 현행과 비슷한 포트폴리오 |
| `rules` | live rule 매칭 합집합만 (상한 TRADED_TOP_N, 초과 시 rule 기대값 순). **매칭 0 = 그날 무거래** | 최종 형태 — "거래 안 함이 기본값" |

- 점수 계산·저장·rank_no 는 **모든 모드에서 현행 그대로 유지**한다(대조군 평가와 프론트
  표시에 계속 필요). 바뀌는 것은 `selected`/핸드오프 대상 판정뿐 —
  `_save_phase2_reports` 의 `is_selected` 로직만 수정하며 **trading_engine.py(가드 파일)는
  건드리지 않는다**.
- veto rule 은 모드와 무관하게 selected 판정 직전에 적용(매칭 시 선정 제외 + 사유 로깅).
  veto 만 먼저 켜는 중간 단계(`legacy`+veto)도 가능하며, 이는 게이트 조건이 완화된다
  (README §5-4 reduce-only 예외).

## 2. rule_id 귀속 관통 (attribution)

목적: 모든 원(₩)이 "어느 가설의 돈인지"를 달고 다니게 한다.

### 스키마 (trading DB)

`trading/sql` 마이그레이션 — `trade_signal` 에 nullable 컬럼 1개:

```sql
ALTER TABLE trade_signal
  ADD COLUMN rule_names VARCHAR(200) DEFAULT NULL COMMENT '선정 근거 edge_rule name 목록(콤마) — NULL=legacy 점수 선정';
```

- **trading 도메인 로직은 무변경.** risk_engine·execution_engine·seed_allocator 는 이 컬럼을
  읽지 않는다(하위호환). 실현손익→rule 귀속은 `trade_signal ⨝ audit_log/fill` 조인으로
  jongalab 쪽(rule_evaluator 확장 또는 조회 시점)에서 계산한다.
- 한 종목이 여러 rule 에 동시 매칭되면 콤마 목록으로 기록하고, 귀속 손익은 매칭 rule 들에
  균등 분할한다(단순함 우선 — 정교한 배분은 필요해질 때).

### 코드

| 파일 | 변경 |
|---|---|
| `workers/closing_bet.py` | 모드 분기 + veto 적용 + signals dict 에 `rule_names` 추가 |
| `core/repository/trade_signal.py` (jongalab) | `push_trade_signals` 에 rule_names 전달 (컬럼 없으면 무시하는 방어 유지) |
| `core/edge_selection.py` (신규) | 모드별 선정 함수 — 순수 로직으로 분리해 pytest 대상化: `select(mode, candidates, live_rules, veto_rules, top_n) -> (selected_codes, rule_names_by_code, veto_log)` |
| `jongalab/tests/test_edge_selection.py` | 모드 3종 × veto × 상한 초과 × 매칭 0 케이스 |

## 3. 사이징과 regime_gate 의 관계

- 시드 배분은 현행 trading 의 등가중 그대로 둔다(메모리: 점수 사이징은 반증됨). rule 단위
  차등(승격 초기 0.5 가중 등)은 **trade_signal 의 rank_no 를 rule 기대값 순으로 부여**하는
  것으로 근사한다 — seed_allocator 가 "점수순 상위 선정·등가중"이므로 rank 만으로 개입 가능,
  trading 수정 불필요.
- `regime_gate`(점수 판별력 기반 시드 축소)는 rules 모드에서 논리적 전제가 사라진다.
  전환 시점에 함께 검토(대체: live rule 들의 최근 rolling mean_net 기반 게이트) — 단
  regime_gate 수정은 trading 도메인이므로 **별도 승인 후 진행**. 그 전까지는 hybrid 모드로
  공존(점수가 계속 계산되므로 게이트도 계속 동작).

## 4. 롤백

`EDGE_SELECTION_MODE=legacy` 환원 한 줄로 즉시 원상 복구(다음 closing_bet 실행부터).
rule_names 컬럼은 nullable 이라 잔존해도 무해.

## 5. 검증

1. `test_edge_selection.py` pytest 통과.
2. paper 모드에서 `hybrid`/`rules` 로 closing_bet 단발 실행 → selected·trade_signal·rule_names
   확인, 매칭 0 인 날 무거래 확인(rules 모드).
3. trading 파이프라인 회귀: `uv run --directory trading --group dev pytest` (자금 경로 무변경 확인).
4. 전환 후 2주간 hybrid 성적을 legacy 페이퍼(control rule)와 병행 비교 — 이 비교 자체가
   Edge Ledger 로 자동 기록된다.

## 6. 완료 기준 (DoD)

- [ ] 모드 스위치·veto·rule_names 귀속이 동작하고 즉시 롤백 가능하다.
- [ ] 실현손익이 rule 별로 조회된다(스코어보드 연동은 Phase 5).
- [ ] trading 민감 파일 무변경, 자금 경로 pytest 통과.
- [ ] `jongalab/README.md`·`trading/README.md`(trade_signal 계약 변경분) 갱신.
