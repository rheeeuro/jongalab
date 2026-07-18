-- 차트 구조 피처(전고점·라운드피겨) + 매물벽 음의 가설 시드 (2026-07-19)
--
-- 목적: 기술적 '가격 레벨' 축(전고점 매물벽·라운드피겨 매도벽)을 실험실 검증 대상으로 올린다.
-- 추가 API 콜 0 — closing_bet 이 이미 종목당 1콜 하던 일봉(ka10081, vol_ratio 용)에서
-- 고가를 함께 파싱하고, 라운드피겨는 현재가만으로 계산한다(core.edge_features 순수 함수).
-- 전부 선정 시점(13~15시) 계산이라 SELECTION_TIME_COLS 자격 — 검증 시 live 승격 가능.
--
--   dist_prior_high_pct — 직전 250거래일 전고점(고가 기준, 당일 제외) 대비 현재가 거리(%).
--                         음수=전고점 아래(매물벽까지 남은 거리), 양수=돌파.
--                         당일 제외 이유: 포함하면 급등주는 항상 자기 자신이 전고점이 되어
--                         매물벽 정보가 사라진다. 직전 이력 20일 미만(신규상장)은 NULL.
--   round_dist_pct      — 최근접 라운드피겨(1·2·5 × 10^k 원 그리드) 대비 거리(%).
--                         음수=직하단(위에 지정가 매도벽), 양수=돌파 직후.
--
-- 비고: 전저점/지지 피처는 만들지 않는다 — 유니버스(당일 거래대금 상위·급등 중심)에
-- 전저점 부근 종목이 사실상 없어 매칭 0 으로 표본이 쌓이지 않는다(2026-07-19 점검).
-- 신고가 돌파(양의 가설)는 기존 f5_breakout_structure 가 검증 중이라 신규 등록하지 않는다.

ALTER TABLE daily_stock_report
    ADD COLUMN dist_prior_high_pct FLOAT DEFAULT NULL COMMENT '250일 전고점(고가, 당일 제외) 대비 현재가 거리(%) — 음수=매물벽 아래, 양수=돌파' AFTER market,
    ADD COLUMN round_dist_pct FLOAT DEFAULT NULL COMMENT '최근접 라운드피겨(1·2·5×10^k원) 대비 현재가 거리(%) — 음수=직하단' AFTER dist_prior_high_pct;

-- ★ 사전 등록 원칙: 임계값은 등록 시점에 고정, 이후 조정은 '새 rule 재등록'으로만.
--   피처 축적은 다음 closing_bet 실행부터 — 그 이전 날짜는 NULL=매칭 실패로 자연 제외.
--   둘 다 음의 가설(기대: 매칭 종목 mean_net ≤ 0)이라 role=veto candidate 로 등록,
--   페이퍼 검증 후 관리자 API 승격(veto_bio_kosdaq 과 동일 경로).

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES

-- 전고점 매물벽 — f5_breakout_structure(돌파 지속)와 경합하는 가설: 벽을 '못 뚫은' 종목만 잡는다.
('veto_prior_high_wall', '전고점 매물벽 경보', 'f5_supply', 'veto',
 '전고점 매물벽 경보(음의 가설): 당일 +3% 이상 급등으로 250일 전고점 직하단(-5%~-1%)에 도달했지만 아직 못 뚫은 종목은, 전고점 부근에 물린 보유자들의 본전 매도 물량이 익일 시가부터 출회되어 갭 상승을 누른다는 veto 가설. -1% 안쪽·돌파는 매물 소화 영역이라 제외 — 돌파 지속(양의 가설)은 f5_breakout_structure 가 별도 검증 중이며, 두 가설의 페이퍼 성적이 "전고점 근처"의 손익 분기(벽 vs 돌파)를 실측으로 가른다.',
 '[{"col":"dist_prior_high_pct","op":"between","value":[-5,-1]},{"col":"change_pct","op":">=","value":3}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- 라운드피겨 매도벽 — 심리 앵커 레벨 직하단 마감의 익일 시가 캡.
('veto_round_figure_cap', '라운드피겨 상단 경보', 'f5_supply', 'veto',
 '라운드피겨 상단 경보(음의 가설): 라운드피겨(1·2·5×10^k원 — 예: 10,000/20,000/50,000원) 직하단 2% 이내에서 마감한 종목은 해당 레벨에 걸린 심리적 지정가 매도 물량이 익일 시가 상단을 캡해 오버나이트 기대값이 깎인다는 veto 가설. 효과 크기가 작을 수 있어 표본으로 실측한다.',
 '[{"col":"round_dist_pct","op":"between","value":[-2,0]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
