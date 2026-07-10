-- 바이오/제약 veto (2026-07-10) — HLB 하한가 사건 대응
--
-- 배경: 2026-07-09 종가베팅이 HLB(028300)를 매수 → 밤사이 리보세라닙 FDA CRL(허가 불발) →
-- 익일 하한가(-30%)로 손절 자체가 물리적으로 불가했다. 종가베팅은 오버나이트 보유 전략인데
-- 바이오는 임상·허가 등 오버나이트 바이너리 이벤트 밀도가 가장 높고, 실거래 표본(6종목)에서도
-- 바이오 실현손익 엣지가 없어(+4,334원, 사실상 본전) 제외해도 포기하는 수익이 없다.
--
-- 구성:
--   ① daily_stock_report.is_bio — closing_bet 이 선정 시점에 굽는 분류 컬럼
--      (core/edge_features.is_bio: 키움 업종명 '제약' + 사명 키워드 + 알려진 예외 코드 3단 판별.
--       키움 upName 은 코스닥 바이오벤처를 '일반서비스'로 뭉뚱그려 업종명만으론 구멍이 남).
--   ② edge_rule 'veto_bio' (role=veto, 즉시 live) — 전 모드에서 선정 직전 제외(reduce-only).
--      rule_evaluator 가 매일 채점하므로 "바이오 제외가 얼마를 아꼈나/놓쳤나"가 자동 측정된다.
--      재평가(해제)는 관리자 API 강등으로 — 코드 변경 불필요.
--
-- 과거 행은 is_bio NULL → predicate 매칭 실패(보수적) — 소급 채점 없음, 표본은 등록일부터.

ALTER TABLE daily_stock_report
  ADD COLUMN is_bio TINYINT NULL COMMENT '바이오/제약 여부(선정 시점 파생 — core.edge_features.is_bio)'
  AFTER frgn_exhaust_chg;

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('veto_bio', '바이오 이벤트 리스크 제외', 'f7_risk', 'veto',
 '꼬리 절단(reduce-only): 바이오/제약은 임상·허가(FDA) 등 오버나이트 바이너리 이벤트 밀도가 가장 높은데, 하한가에선 손절이 물리적으로 불가해 종가베팅의 하드스톱이 무력화된다(2026-07-10 HLB FDA CRL 하한가, 포트 -8% 실측). 실거래 표본상 바이오 엣지 없음(6종목 +4,334원) — 제외해도 포기하는 기대수익이 없다. 판별은 선정 시점 파생 is_bio(업종명+사명 키워드+예외 코드). 페이퍼 채점이 누적되면 mean_net 으로 제외 비용을 재평가한다.',
 '[{"col":"is_bio","op":"==","value":1}]',
 'exec_leg_ret', 'live', 40, CURDATE());
