-- edge_rule 한글 제목(title) 추가 (2026-07-06)
-- 목적: 실험실 카드 제목이 family 라벨("수급 전략" 등 7종)뿐이라 같은 family 가설이
--       늘수록(현재 수급 13장) 화면에서 구분이 안 되던 문제 해결. 제목은 가설의 속성이라
--       프론트 사전이 아닌 데이터로 관리한다. 신규 등록은 API(RuleCreate.title)가 필수로 받고,
--       title 이 NULL 인 행은 프론트가 name 슬러그로 폴백한다.

ALTER TABLE edge_rule
    ADD COLUMN title VARCHAR(80) DEFAULT NULL COMMENT '카드 제목(한글) — NULL 이면 프론트가 name 폴백' AFTER name;

-- 기존 가설 백필 (등록 시점 카탈로그 24종, name 기준이라 재실행/신규 설치 무해)
UPDATE edge_rule SET title = '현행 점수 Top10 기준선'          WHERE name = 'control_legacy_top10';
UPDATE edge_rule SET title = '질 좋은 야간 갭 (섹터 동조)'      WHERE name = 'f3_nxt_gap_quality';
UPDATE edge_rule SET title = '얇은 야간 갭 착시 (음의 가설)'    WHERE name = 'f3_nxt_gap_thin';
UPDATE edge_rule SET title = '신선한 재료 미반영'               WHERE name = 'f1_fresh_news_unpriced';
UPDATE edge_rule SET title = '조용하던 종목 언급 폭증'          WHERE name = 'f1_news_surprise_burst';
UPDATE edge_rule SET title = '미 반도체 강세 후발주'            WHERE name = 'f2_us_semis_laggard';
UPDATE edge_rule SET title = '섹터 대장 급등 후발주'            WHERE name = 'f4_sector_follower';
UPDATE edge_rule SET title = '과열 + 야간 추가급등 제외'        WHERE name = 'veto_overheat_gap';
UPDATE edge_rule SET title = '악재 뉴스 제외'                   WHERE name = 'veto_bad_news';
UPDATE edge_rule SET title = '기관·외인 동반 연속 매수'         WHERE name = 'f5_inst_frgn_dual_buy';
UPDATE edge_rule SET title = '개인 단독 급등 (음의 가설)'       WHERE name = 'f5_retail_solo_pump';
UPDATE edge_rule SET title = '신고가 정배열 돌파'               WHERE name = 'f5_breakout_structure';
UPDATE edge_rule SET title = '외국계 창구 집중 매수'            WHERE name = 'f5_foreign_broker_top';
UPDATE edge_rule SET title = '오후장 마감 강세'                 WHERE name = 'f5_late_day_strength';
UPDATE edge_rule SET title = '거래량 5배 폭증'                  WHERE name = 'f5_volume_surprise';
UPDATE edge_rule SET title = '프로그램 4일+ 연속 매수'          WHERE name = 'f5_prog_persistent';
UPDATE edge_rule SET title = '거래대금 상위 첫 등장'            WHERE name = 'f5_universe_new_entry';
UPDATE edge_rule SET title = '테마 급등 후발주'                 WHERE name = 'f4_theme_follower';
UPDATE edge_rule SET title = '외인 소진율 상승'                 WHERE name = 'f5_frgn_exhaust_rise';
UPDATE edge_rule SET title = '수급점수 D밴드 (0~40)'            WHERE name = 'f5_supply_band_d';
UPDATE edge_rule SET title = '수급점수 C밴드 (40~55)'           WHERE name = 'f5_supply_band_c';
UPDATE edge_rule SET title = '수급점수 B밴드 (55~70)'           WHERE name = 'f5_supply_band_b';
UPDATE edge_rule SET title = '수급점수 A밴드 (70+)'             WHERE name = 'f5_supply_band_a';
