-- edge_rule 역할(role) 분리 마이그레이션 (2026-07-09)
--
-- 배경: 지금까지 rule 의 역할(selector/veto/benchmark)을 family 에서 파생했다
-- (edge_policy.FAMILY_ROLES). 이 결합이 두 가지 어긋남을 만들었다:
--   ① 수급 밴드 4종(f5_supply_band_a~d)은 유니버스를 수급점수 구간으로 분할한 **측정 도구**인데
--      family=f5_supply 라서 selector 취급 — 통계 게이트를 우연히 통과하면 광역 매칭 rule 이
--      실탄(live 선정)으로 승격될 구조적 위험이 있었다.
--   ② veto rule 은 도메인이 제각각(뉴스/NXT/수급/시간외)인데 전부 family='veto' 로 뭉뚱그려져
--      도메인 그룹핑이 불가능했다(역할이 family 자리를 차지).
-- 해소: role 컬럼을 명시 속성으로 추가하고, family 는 순수 도메인 축으로 되돌린다.
--   role     : selector(선정) / veto(제외 전용) / benchmark(측정·기준선 — 선정에 안 씀)
--   family   : f1_news / f2_global / f3_nxt / f4_laggard / f5_supply / f6_ah / control
--
-- ⚠️ 데이터 영향 없음: predicate·registered_at·stats·edge_rule_daily(채점 이력)는 건드리지
--    않는다. 분류 메타데이터(role·family)만 바로잡으므로 사전 등록 원칙과 충돌하지 않는다.
-- 신규 DB 세팅 시 실행 순서: 시드(8·14)가 구 체계(family='veto' 등)로 INSERT 한 뒤
-- 이 파일이 name 기준으로 재분류하므로 순서대로 실행하면 결과가 동일하다.

ALTER TABLE edge_rule
  ADD COLUMN role VARCHAR(10) NOT NULL DEFAULT 'selector' AFTER family;

-- ① 역할 백필 — 구 family 겸용 체계 → 명시 role
UPDATE edge_rule SET role = 'veto'      WHERE family = 'veto';
UPDATE edge_rule SET role = 'benchmark' WHERE family = 'control';

-- ② 수급 밴드 4종 → benchmark (측정 도구, 매수 선정 대상 아님)
UPDATE edge_rule SET role = 'benchmark'
 WHERE name IN ('f5_supply_band_a', 'f5_supply_band_b', 'f5_supply_band_c', 'f5_supply_band_d');

-- ③ veto rule 의 family 를 실제 도메인으로 재배치
UPDATE edge_rule SET family = 'f1_news'   WHERE name = 'veto_bad_news';
UPDATE edge_rule SET family = 'f3_nxt'    WHERE name = 'veto_overheat_gap';
UPDATE edge_rule SET family = 'f5_supply' WHERE name IN ('veto_short_surge', 'veto_credit_high');
UPDATE edge_rule SET family = 'f6_ah'     WHERE name = 'veto_ah_react_down';
