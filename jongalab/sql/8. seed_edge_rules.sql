-- 초기 가설 카탈로그 시드 (Phase 3.5, 2026-07-04)
-- 각 rule 은 인과 근거(누가 왜 내일 아침 사는가)를 갖고 candidate 로 시작한다
-- (control·veto 는 즉시 live). registered_at=CURDATE() 가 승격 판정의 out-of-sample 표본 시작일.
--
-- ★ 사전 등록 원칙: 등록 후 임계값을 옮기면 '새 rule 로 재등록'한다(같은 rule 조건 몰래 튜닝 금지).
-- INSERT IGNORE 로 재실행해도 기존 행(=registered_at)을 보존한다 — 표본 시작일이 흔들리지 않게.
-- exit_label 은 전부 exec_leg_ret(기본). 청산창 변주는 별도 비교 rule 로 등록한다.
--
-- F2 sector 목록: 계획의 예시 명(["반도체","전기전자","IT부품"])은 실제 업종명과 달라, 실 DB
-- 업종명 '전기/전자'(삼성전자·SK하이닉스 등 주요 반도체 포함, 표본 확보 우선)로 확정(사용자 승인).

INSERT IGNORE INTO edge_rule (name, family, description, predicate, exit_label, status, min_sample, registered_at) VALUES

-- 대조군 (즉시 live, 영구 유지) — 모든 신규 rule 이 이겨야 할 상대 기준. 점수 로직이 바뀌어도 selected 정의가 추적.
('control_legacy_top10', 'control',
 '현행 종합점수 상위 10(selected=1) 기준선. 모든 신규 가설이 절대(비용초과)·상대(대조군 우위) 양쪽으로 이겨야 한다.',
 '[{"col":"selected","op":"==","value":1}]',
 'exec_leg_ret', 'live', 40, CURDATE()),

-- F3 NXT 괴리형 — 본장 유동성 재진입자. 애프터마켓은 참여자가 적어 덜 효율적, 실수요 괴리는 익일 본장에서 재정렬.
('f3_nxt_gap_quality', 'f3_nxt',
 '본장 유동성 재진입자: 애프터마켓 실수요가 만든 질 좋은 NXT 괴리(1~6%)는 익일 본장 유동성이 붙으며 재정렬된다. 섹터 동조(sector_rel_ret>=0)로 착시 배제.',
 '[{"col":"nxt_gap_pct","op":"between","value":[1.0,6.0]},{"col":"nxt_listed","op":"==","value":1},{"col":"sector_rel_ret","op":">=","value":0},{"col":"change_pct","op":"between","value":[0,12]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F3 음의 가설(대우 검증) — 섹터 동조 없는 단독 NXT 괴리는 얇은 호가 착시. 기대 mean_net<=0. 양(+)이면 F3 인과 재검토.
('f3_nxt_gap_thin', 'f3_nxt',
 '착시 검증용 음의 가설: 섹터 동조 없이(sector_rel_ret<0) 단독으로 큰 NXT 괴리(>=3%)는 얇은 호가 착시라 익일 수익이 안 된다는 대우 명제. F3 본가설의 인과 논리를 반증가능하게 만든다.',
 '[{"col":"nxt_gap_pct","op":">=","value":3},{"col":"sector_rel_ret","op":"<","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F1 뉴스 미반영형 — 장 마감 후 해석 매수자. 새 재료(14일 내 첫 언급)인데 당일 반응 미미하면 반영 여지가 남는다.
('f1_fresh_news_unpriced', 'f1_news',
 '장 마감 후/저녁 해석 매수자: 14일 내 첫 등장한 신선한 재료(오후 언급 존재)인데 당일 가격 반응이 부족한(0~5%) 종목은 아침에 재가격화된다. 시장이 보고 무시했을 가능성도 있어 검증 대상.',
 '[{"col":"news_first_today","op":"==","value":1},{"col":"news_unique_count","op":">=","value":2},{"col":"change_pct","op":"between","value":[0,5]},{"col":"news_pm_count","op":">=","value":1}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F1 서프라이즈 폭증 — 평소 조용하던 종목의 언급 폭증은 관심 유입 선행 신호.
('f1_news_surprise_burst', 'f1_news',
 '관심 유입 선행: 평소 조용하던 종목(직전 7일 평균 언급<=0.5)의 당일 언급 폭증(고유 기사>=3)은 새 관심의 서프라이즈 신호이며, 적당한 상승(2~12%)과 함께면 익일 추종 매수를 부른다.',
 '[{"col":"news_prior_avg","op":"<=","value":0.5},{"col":"news_unique_count","op":">=","value":3},{"col":"change_pct","op":"between","value":[2,12]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F2 해외 동조 지연형 — 아침 섹터 리밸런싱. 미 반도체 강한 밤, 국내 반도체 중 덜 오른 종목이 아침에 따라간다.
('f2_us_semis_laggard', 'f2_global',
 '아침 섹터 리밸런싱 매수자: 미국 반도체(SOX>=1.5%)가 강한 밤이면, 국내 전기/전자 중 당일 섹터 대비 덜 반응한(sector_rel_ret<=0) 종목이 아침에 해외 참조가격을 따라간다.',
 '[{"col":"market.sox_ret","op":">=","value":1.5},{"col":"sector","op":"in","value":["전기/전자"]},{"col":"sector_rel_ret","op":"<=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F4 후발 확산형 — 대장주를 놓친 추격 매수자. 관심이 동섹터 후발주로 이동.
('f4_sector_follower', 'f4_laggard',
 '대장주를 놓친 추격 매수자: 동섹터 대장이 급등(sector_leader_chg>=8%)했는데 대장이 아닌 후발주(is_leader=0)가 아직 저반응(sector_rel_ret -3~0)이면, 관심 이동으로 익일 따라 오른다.',
 '[{"col":"is_leader","op":"==","value":0},{"col":"sector_leader_chg","op":">=","value":8},{"col":"sector_rel_ret","op":"between","value":[-3,0]},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- veto 과열 갭 (candidate — ⚠️ 선정 시점 실행 불가) — 당일 과열 + NXT 추가 급등은 익일 시초가 고점 리스크.
-- nxt_gap_pct 는 19:50 수집인데 선정은 13~15시(KRX)·매수는 19:30(NXT)이라, live 여도 선정 veto 로는
-- 절대 발동하지 못한다(core.edge_policy 실행 가능성 게이트가 승격을 차단). 페이퍼로 가설만 검증하고,
-- 선정/집행 시점을 19:50 이후로 옮기는 설계 변경이 있을 때 승격을 재검토한다. (2026-07-05 리뷰 반영: live→candidate)
('veto_overheat_gap', 'veto',
 '꼬리 절단(reduce-only): 당일 +15% 이상 과열에 NXT 애프터 추가 급등(>=5%)까지 겹치면 내가 매수하는 시점엔 이미 남에게 넘길 구간 — 익일 시초가 고점 리스크. ⚠️ nxt_gap_pct 는 19:50 수집이라 현 선정 시점(13~15시)엔 실행 불가 — 페이퍼 검증 전용, 집행 설계 변경 후 승격 재검토.',
 '[{"col":"change_pct","op":">=","value":15},{"col":"nxt_gap_pct","op":">=","value":5}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- veto 악재 뉴스 (즉시 live, reduce-only) — LLM 재료 방향 부정. news_sentiment 는 top-10 후보만 라벨이라 커버리지 한계, 결측 시 미적용이 안전 기본값.
('veto_bad_news', 'veto',
 '꼬리 절단(reduce-only): LLM 재료 방향이 부정적(news_sentiment<=30)이고 복수 고유 기사(>=2)로 확인되면 악재 노출을 제외한다. news_sentiment 는 top-10 후보만 라벨링돼 커버리지 한계가 있고, 결측(NULL)은 매칭 실패=미적용이 안전 기본값.',
 '[{"col":"news_sentiment","op":"<=","value":30},{"col":"news_unique_count","op":">=","value":2}]',
 'exec_leg_ret', 'live', 40, CURDATE());
