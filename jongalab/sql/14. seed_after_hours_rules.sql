-- 시간외·리스크 라벨 가설 시드 (2026-07-09)
-- after_hours_labels 워커(17:50)가 채우는 라벨(ah_*·신용·공매도·체결강도) 기반 가설 5종.
-- 전부 candidate — rule_evaluator 가 매일 자동 채점하고, 7월말 표본으로 유지/폐기 판정.
--
-- ⚠️ 전 rule 이 17:50 수집 컬럼을 쓰므로 **선정 시점(13~15시) 실행 불가** — live 승격은
--    edge_policy 실행 가능성 게이트가 차단한다(veto_overheat_gap 과 동일한 페이퍼 전용 지위).
--    신용/공매도는 T-1 확정치라, 유효 판정 시 closing_bet 이 선정 시점에 직접 조회(종목당 +2콜)
--    하거나 전일 라벨을 참조하는 집행 설계 변경 후 재등록·승격을 검토한다.
-- ★ 사전 등록 원칙: 임계값은 2026-07-09 유니버스(n=43) 실측 분포(p90 부근)로 고정.
--    이후 조정은 '새 rule 재등록'으로만 한다. INSERT IGNORE 로 registered_at 보존.
-- 라벨 축적은 7/9 저녁부터(ah_* 는 7/10부터 정상) — 그 이전 날짜는 NULL=매칭 실패로 자연 제외.

INSERT IGNORE INTO edge_rule (name, title, family, description, predicate, exit_label, status, min_sample, registered_at) VALUES

-- F6 시간외 반응 지속 — 시간외단일가 매수자는 종가 이후 재료를 본 정보 우위 참여자. 유의미한
-- 체결량(1만주+)이 실린 초과반응(+1.5%p+)은 익일 본장 유동성에서 이어진다는 가설.
('f6_ah_react_up', '시간외 반응 지속', 'f6_ah',
 '시간외 정보 우위 매수자: 당일 KRX 종가 대비 시간외단일가가 +1.5% 이상(체결 1만주+ 실림)이면 마감 후 재료를 본 매수세가 익일 시초가로 이어진다. 과열(15%+) 종목은 제외.',
 '[{"col":"ah_react","op":">=","value":1.5},{"col":"ah_volume","op":">=","value":10000},{"col":"change_pct","op":"between","value":[0,15]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F6 음의 가설(veto) — 시간외 음전은 마감 후 악재/차익 실현 신호, 익일 시초가 약세.
('veto_ah_react_down', '시간외 이탈 경보', 'veto',
 '시간외 이탈 경보: 당일 상승 마감했더라도 시간외단일가가 종가 대비 -1.5% 이상 밀리면(체결 1만주+) 마감 후 악재·차익실현 신호로 익일 시초가가 약하다는 veto 가설.',
 '[{"col":"ah_react","op":"<=","value":-1.5},{"col":"ah_volume","op":">=","value":10000}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- veto 공매도 집중 — 공매도 비중 상위(T-1 15%+, 7/9 유니버스 p90≈13.6)는 하방 베팅 집중 종목.
('veto_short_surge', '공매도 집중 경보', 'veto',
 '공매도 집중 경보: 전일 공매도 매매비중 15% 이상(유니버스 상위 ~10%)은 기관 하방 베팅이 집중된 종목으로, 상승일에도 익일 되돌림 리스크가 크다는 veto 가설.',
 '[{"col":"short_wght","op":">=","value":15}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- veto 신용잔고 과열 — 신용잔고율 상위(T-1 3%+, 7/9 유니버스 p90≈2.4)는 반대매매 취약.
('veto_credit_high', '신용잔고 과열 경보', 'veto',
 '반대매매 취약 경보: 신용융자 잔고율 3% 이상(유니버스 상위 ~10%)은 하락 시 반대매매가 낙폭을 증폭시키는 구조라, 오버나이트 보유의 꼬리 리스크가 크다는 veto 가설.',
 '[{"col":"credit_remn_rt","op":">=","value":3}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- F5 체결강도 강세 마감 — 공격적 매수(시장가 매수 우위)로 마감한 종목의 모멘텀 지속.
('f5_exec_str_strong', '체결강도 강세 마감', 'f5_supply',
 '공격 매수 마감 지속: 당일 체결강도 120 이상(유니버스 상위 ~10%, 매수 우위 마감) + 양전 종목은 미체결 매수 수요가 익일 시초가로 이월된다는 가설.',
 '[{"col":"exec_str","op":">=","value":120},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());

-- 기존 등록 행 title 백필 (INSERT IGNORE 는 이미 있는 행을 갱신하지 않으므로 별도 UPDATE — 재실행 멱등)
UPDATE edge_rule SET title = '시간외 반응 지속'    WHERE name = 'f6_ah_react_up'     AND title IS NULL;
UPDATE edge_rule SET title = '시간외 이탈 경보'    WHERE name = 'veto_ah_react_down' AND title IS NULL;
UPDATE edge_rule SET title = '공매도 집중 경보'    WHERE name = 'veto_short_surge'   AND title IS NULL;
UPDATE edge_rule SET title = '신용잔고 과열 경보'  WHERE name = 'veto_credit_high'   AND title IS NULL;
UPDATE edge_rule SET title = '체결강도 강세 마감'  WHERE name = 'f5_exec_str_strong' AND title IS NULL;
