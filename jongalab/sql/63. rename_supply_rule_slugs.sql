-- 수급 3종 슬러그(edge_rule.name) 교체 + rule_names 백필 (2026-08-10)
-- sql/62 에서 카드 제목만 바꿨으나, 실험실 상세 URL(`/lab/<name>`)과 상세 하단 mono 표기에
-- 은어 슬러그가 남아 사용자에게 그대로 노출된다는 지적 → 슬러그도 조건이 읽히는 이름으로 교체.
--
--   f5_supply_missile    → f5_bottom_entry_dual_buy   (바닥권 첫 등장 + 외인·기관 동반 매수)
--   f5_supply_eagle      → f5_frgn_surge_flat34       (외인 대량 매수 후 3~4일 횡보)
--   f5_supply_inflection → f5_supply_turn_vol2        (순매수 전환 첫날 + 거래량 2배)
--
-- 표본·판정은 그대로다: edge_rule.id 불변 → edge_rule_daily.rule_id 참조가 유지되고,
-- predicate/status/registered_at/decided_* 도 건드리지 않는다(f5_frgn_surge_flat34 는 live).
-- family 는 'f5_supply' 로 유지(edge_policy.FAMILIES 상수와 맞물린 값이라 별개 축).
--
-- 슬러그 문자열을 저장하는 곳은 두 군데뿐이고 둘 다 이 마이그레이션에서 백필한다:
--   1) jongalab.daily_stock_report.rule_names (아래)
--   2) trading.trade_signal.rule_names → trading/sql/5. backfill_supply_rule_slugs.sql
-- edge_rule_daily.matched 는 종목 코드/명만 담아 영향 없다.

-- 1) 룰 슬러그 교체
UPDATE edge_rule SET name = 'f5_bottom_entry_dual_buy' WHERE name = 'f5_supply_missile';
UPDATE edge_rule SET name = 'f5_frgn_surge_flat34'     WHERE name = 'f5_supply_eagle';
UPDATE edge_rule SET name = 'f5_supply_turn_vol2'      WHERE name = 'f5_supply_inflection';

-- 2) 과거 선정 근거 태깅 백필 (콤마 목록 안의 부분 문자열 치환 — 세 슬러그는 서로 접두어가
--    아니라서 치환 순서에 무관하다)
UPDATE daily_stock_report
   SET rule_names = REPLACE(rule_names, 'f5_supply_missile', 'f5_bottom_entry_dual_buy')
 WHERE rule_names LIKE '%f5_supply_missile%';
UPDATE daily_stock_report
   SET rule_names = REPLACE(rule_names, 'f5_supply_eagle', 'f5_frgn_surge_flat34')
 WHERE rule_names LIKE '%f5_supply_eagle%';
UPDATE daily_stock_report
   SET rule_names = REPLACE(rule_names, 'f5_supply_inflection', 'f5_supply_turn_vol2')
 WHERE rule_names LIKE '%f5_supply_inflection%';
