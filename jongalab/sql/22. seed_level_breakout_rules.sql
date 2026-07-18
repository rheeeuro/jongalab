-- 전고점·라운드피겨 '돌파' 양의 가설 시드 (2026-07-19 — sql/20 매물벽 veto 의 대칭 쌍)
--
-- 배경: sql/20 은 레벨 '직하단'(못 뚫음)의 음의 가설만 등록했다. 같은 축의 '돌파' 영역을
-- 양의 가설로 등록해 축을 대칭으로 측정한다 — 손익 분기(벽 vs 돌파)가 어디인지는
-- 데이터가 판정한다. 신규 컬럼 없음(sql/20 피처 재사용), 시드 전용.
--
-- ★ 사전 점검 (2026-07-19, 6/26~7/15 유니버스 재현, 참고용 — 승격 근거 아님):
--   유니버스 기준선 +0.18%(n=345).
--   전고점 돌파[0,5]&chg>=3: n=9 mean −2.64% t=−2.1 승률 33% — **인샘플 역방향**(돌파가 나빴음).
--   매물벽[-5,-1]&chg>=3(등록된 veto): n=4 mean +1.70% — 이것도 역방향(직하단이 좋았음).
--   라운드피겨 돌파[0.1,2]&chg>=0: n=6 mean −0.55% — 무엣지.
--   전부 표본 극소 — 방향이 뒤집혀 있다는 것 자체가 축 대칭 측정이 필요한 이유.
--   검증 결과 음(−)이 확정되면 selector 승격 대신 veto 재등록 후보가 된다.

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES

('f5_prior_high_break', '전고점 돌파 지속', 'f5_supply', 'selector',
 '신고가 돌파 추세추종 매수자: 당일 +3% 이상 상승으로 250일 전고점을 실제로 넘어선(0~+5%) 종목은 머리 위 매물이 없어 아침 후속 자금이 붙는다는 양의 가설. veto_prior_high_wall(직하단 -5%~-1%, 음의 가설)의 대칭 쌍 — 같은 축의 손익 분기를 데이터로 가른다. f5_breakout_structure(정배열+52주 종가고점 95% 근처)와 달리 고가 기준 실제 돌파만 잡는다. 사전 점검(6/26~7/15 인샘플, 참고용): n=9, next_open_ret −2.64%(t=−2.1) — 역방향 주의, 음이 확정되면 veto 재등록 후보.',
 '[{"col":"dist_prior_high_pct","op":"between","value":[0,5]},{"col":"change_pct","op":">=","value":3}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

('f5_round_figure_break', '라운드피겨 돌파 지속', 'f5_supply', 'selector',
 '라운드피겨 돌파 확인 매수자: 라운드피겨(1·2·5×10^k원)를 상향 돌파한 직후(+0.1%~+2%, 상승 마감)는 해당 레벨의 심리적 매도벽이 소화된 상태라 익일 저항이 얇다는 양의 가설. veto_round_figure_cap(직하단 -2%~0, 음의 가설)의 대칭 쌍. 사전 점검(6/26~7/15 인샘플, 참고용): n=6, next_open_ret −0.55% — 무엣지, out-of-sample 로 판정.',
 '[{"col":"round_dist_pct","op":"between","value":[0.1,2]},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
