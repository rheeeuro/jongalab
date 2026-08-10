-- 수급 3종 슬러그 교체에 따른 rule_names 백필 (2026-08-10)
-- 짝 마이그레이션: jongalab/sql/63. rename_supply_rule_slugs.sql (거기서 edge_rule.name 교체)
-- trade_signal.rule_names 는 귀속 기록 전용이라 집행 로직(risk_engine·execution_engine·
-- seed_allocator)은 이 값을 읽지 않는다 — 실현손익 → rule 귀속 조인만 영향받는다.
--
--   f5_supply_missile    → f5_bottom_entry_dual_buy
--   f5_supply_eagle      → f5_frgn_surge_flat34
--   f5_supply_inflection → f5_supply_turn_vol2

USE trading;

UPDATE trade_signal
   SET rule_names = REPLACE(rule_names, 'f5_supply_missile', 'f5_bottom_entry_dual_buy')
 WHERE rule_names LIKE '%f5_supply_missile%';
UPDATE trade_signal
   SET rule_names = REPLACE(rule_names, 'f5_supply_eagle', 'f5_frgn_surge_flat34')
 WHERE rule_names LIKE '%f5_supply_eagle%';
UPDATE trade_signal
   SET rule_names = REPLACE(rule_names, 'f5_supply_inflection', 'f5_supply_turn_vol2')
 WHERE rule_names LIKE '%f5_supply_inflection%';
