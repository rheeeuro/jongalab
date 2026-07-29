-- 음의 가설 rule 2종 → role=veto 재분류 (2026-07-29)
--
-- 배경: 2026-07-07 시드 배치는 음의 가설(착시 검증용)을 **매수 축(selector)** 에 등록했다.
-- 짝이 되는 양의 가설과 같은 자로 재야 대우 검증이 성립한다는 이유였다
--   f5_retail_solo_pump  ↔ f5_inst_frgn_dual_buy (기관·외국인 동반매수)
--   f3_nxt_gap_thin      ↔ f3_nxt_gap_quality    (섹터 동조 NXT 괴리)
-- 그런데 2026-07-19 배치부터는 같은 성격의 음의 가설을 **처음부터 veto 로** 등록했고
-- (veto_prior_high_wall·veto_round_figure_cap), 위 2종만 구 규율의 잔재로 남았다.
--
-- 왜 고치는가 — selector 로 두면 **게이트 부호가 반대로 붙는다**:
--   가설대로 손실   → 게이트 침묵. veto 전환 근거가 쌓여도 아무도 알려주지 않는다(영구 candidate).
--   가설과 반대 이익 → 🟢 '승격 후보'. **착시 검증용 rule 이 실탄 매수 후보로 올라온다.**
-- 실제로 f5_retail_solo_pump 가 2026-07-29 그 상태가 됐다(experimental 정책이 유의성까지
-- 면제해 일 클러스터 t=1.18 로 발견 판정 통과 → confirming). role=veto 면 같은 데이터가
-- '실익 미입증'으로 정상 탈락한다(제외 종목 mean_net +1.897% > 0).
--
-- ⚠️ 채점 이력은 건드리지 않는다: predicate·registered_at·edge_rule_daily 는 그대로이고
--    role·family 는 분류 메타데이터라 사전 등록 원칙과 충돌하지 않는다(sql/15 선례).
--    단 decision 은 **selector 게이트로 찍힌 판정**이라 무효 → NULL 로 되돌려 재판정한다
--    (발견 구간 표본은 이미 육안으로 본 데이터라 '사전등록 1회 검정'은 이 2종에 대해
--     엄밀하지 않다. 그래도 부호가 거꾸로인 게이트로 판정을 남기는 것보다 낫다).
--    stats.promo_* 는 rule_evaluator 가 다음 실행에 veto 게이트로 재계산한다.

-- ① 역할 재분류 — family(도메인)는 그대로 둔다(sql/15 규약: veto 는 도메인 family + role=veto)
UPDATE edge_rule SET role = 'veto'
 WHERE name IN ('f5_retail_solo_pump', 'f3_nxt_gap_thin');

-- ② selector 게이트로 찍힌 판정 기록 무효화 → 다음 판정일에 veto 기준으로 다시 판정
UPDATE edge_rule SET decision = NULL
 WHERE name IN ('f5_retail_solo_pump', 'f3_nxt_gap_thin');

-- ③ 초심자용 설명을 '제외 규칙 후보'로 갱신 (sql/30 규약: description 은 초심자용)
UPDATE edge_rule SET description = '기관·외국인은 파는데 개인 매수만으로 급등한 종목입니다. 받아줄 큰손이 없어 다음 날 도로 빠질 가능성이 높다고 보고, 이런 종목을 매수 후보에서 빼는 것이 이득인지 검증하는 제외 후보 규칙입니다(제외 대상이 평균적으로 손실이어야 정상).' WHERE name = 'f5_retail_solo_pump';
UPDATE edge_rule SET description = '야간 거래에서 혼자만 3% 이상 크게 올랐고 같은 업종은 조용했던 종목입니다. 밤에는 거래가 적어 적은 주문만으로도 가격이 크게 튀는데, 이런 착시 상승을 매수 후보에서 빼는 것이 이득인지 검증하는 제외 후보 규칙입니다(제외 대상이 평균적으로 손실이어야 정상).' WHERE name = 'f3_nxt_gap_thin';

-- ④ 제목도 역할과 맞춘다 — '(음의 가설)' 은 유지하되 제외 후보임을 드러낸다
UPDATE edge_rule SET title = '개인 단독 급등 제외 (음의 가설)'    WHERE name = 'f5_retail_solo_pump';
UPDATE edge_rule SET title = '얇은 야간 갭 착시 제외 (음의 가설)' WHERE name = 'f3_nxt_gap_thin';

-- 확인
SELECT name, family, role, status, title, decision FROM edge_rule
 WHERE name IN ('f5_retail_solo_pump', 'f3_nxt_gap_thin');
