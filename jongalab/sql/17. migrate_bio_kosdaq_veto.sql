-- 바이오 veto 범위 조정: 전면 제외 → 코스닥 바이오만, 검증(candidate) 후 승격 (2026-07-10 저녁)
--
-- 배경: sql/16 의 veto_bio(전면 제외)는 즉시 live 였으나, 사용자 판단(바이오 섹터 상승 국면
-- 전망)에 따라 ① 범위를 코스닥 바이오로 좁히고 ② 페이퍼 검증 후 관리자 API 로 승격하는
-- 구조로 변경한다. 시총 기준(중소형)은 기각 — HLB 가 시총 7조 코스닥 대형주라 '중소형' 컷은
-- 이번 사건 자체를 못 막는다(실측). 거래소 축이 실적 기반(코스피 셀트리온·삼바)과 이벤트
-- 의존(코스닥 신약주)을 더 잘 가른다.
--
-- 구성:
--   ① daily_stock_report.market — closing_bet 이 ka10100 marketName 에서 캡처(추가 API 콜 없음,
--      키움의 '거래소' 표기는 '코스피'로 정규화). NULL(캡처 실패)이면 predicate 매칭 실패=veto
--      미적용(fail-open) — veto 커버리지 구멍이므로 로그로 드러난다.
--   ② edge_rule 'veto_bio_kosdaq' (role=veto, **candidate**) — 코스닥 바이오 전체.
--      rule_evaluator 가 매일 채점 → 검증되면 관리자 API 승격(veto 는 실행 가능성 게이트만).
--   ③ 기존 veto_bio(전면 제외) live→candidate 강등 — 선정 미적용, 채점은 계속되므로
--      '전면 제외 vs 코스닥만 제외'의 페이퍼 성적을 나란히 비교할 수 있다.
--
-- ⚠️ 이 시점부터 live 바이오 veto 는 없다 — veto_bio_kosdaq 승격 전까지 바이오 매수 재개.
--    단일 종목 노출은 seed_allocator 캡(SEED_MAX_NAME_PCT)이 유일한 방어.

ALTER TABLE daily_stock_report
  ADD COLUMN market VARCHAR(10) DEFAULT NULL COMMENT '시장 구분(코스피/코스닥 — ka10100 marketName, 거래소→코스피 정규화)'
  AFTER sector;

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('veto_bio_kosdaq', '코스닥 바이오 제외', 'f7_risk', 'veto',
 '꼬리 절단(reduce-only): 코스닥 바이오는 임상·허가(FDA) 바이너리 이벤트 의존도가 높고 하한가에선 손절이 물리적으로 불가하다(2026-07-10 HLB FDA CRL 하한가, 시총 7조 코스닥 — 시총 컷이 아닌 거래소 축을 쓰는 이유). 실적 기반 코스피 제약(셀트리온·삼바 등)은 허용해 바이오 섹터 랠리 기회비용을 줄인다. veto_bio(전면 제외, candidate 강등)와 페이퍼 성적을 나란히 비교해 검증 후 승격한다.',
 '[{"col":"is_bio","op":"==","value":1},{"col":"market","op":"==","value":"코스닥"}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());

-- 전면 제외 rule 은 검증(비교 측정) 전용으로 강등 — 채점은 계속, 선정 veto 미적용
UPDATE edge_rule SET status = 'candidate' WHERE name = 'veto_bio' AND status = 'live';
