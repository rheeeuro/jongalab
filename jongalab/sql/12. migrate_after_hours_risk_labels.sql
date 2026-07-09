-- 시간외 반응 + 리스크 라벨 (2026-07-09)
-- 목적: 익일 갭 선행지표(시간외단일가)와 악재 veto 연구용 리스크 지표(신용·공매도·대차·체결강도)를
--       관측 컬럼으로 굽는다. 전부 17:50 after_hours_labels 워커가 UPDATE 로만 채우는
--       관측 레이어 — closing_bet 의 upsert(_ANALYSIS_COLS)에 포함되지 않아 재실행에도 보존.
--       점수·선정 무영향(순수 연구 라벨). next_open_ret 등 결과 라벨과 조인해 엣지 검증에 쓴다.
--
--   ah_price / ah_flu_rt / ah_volume — 시간외단일가 현재가·등락률(전일종가 대비)·누적거래량
--                                      (ka10087 — 세션 16~18시 중에만 유효해 17:50 스냅샷)
--   credit_remn_rt — 신용융자 잔고율(%) (ka10013, T-1 확정 — 선정 시점에 알 수 있던 값)
--   short_wght / short_wght_5d — 공매도 매매비중(%) T-1 / 직전 5거래일 평균 (ka10014)
--   lend_remn / lend_irds_5d — 대차 잔고주수 T-1 / 직전 5거래일 증감 합(주) (ka20068)
--   exec_str / exec_str_5d — 당일 체결강도 / 5일 평균 (ka10047, 17:50 수집 — KRX 마감 후라 사실상 확정치)

ALTER TABLE daily_stock_report
    ADD COLUMN ah_price INT DEFAULT NULL COMMENT '시간외단일가 현재가(원) — ka10087 18시 스냅샷',
    ADD COLUMN ah_flu_rt FLOAT DEFAULT NULL COMMENT '시간외단일가 등락률(%) — 전일종가 대비',
    ADD COLUMN ah_volume BIGINT DEFAULT NULL COMMENT '시간외단일가 누적거래량(주)',
    ADD COLUMN credit_remn_rt FLOAT DEFAULT NULL COMMENT '신용융자 잔고율(%) — T-1 확정(ka10013)',
    ADD COLUMN short_wght FLOAT DEFAULT NULL COMMENT '공매도 매매비중(%) — T-1(ka10014)',
    ADD COLUMN short_wght_5d FLOAT DEFAULT NULL COMMENT '공매도 매매비중 직전 5거래일 평균(%)',
    ADD COLUMN lend_remn BIGINT DEFAULT NULL COMMENT '대차 잔고주수 — T-1(ka20068)',
    ADD COLUMN lend_irds_5d BIGINT DEFAULT NULL COMMENT '대차 증감 직전 5거래일 합(주)',
    ADD COLUMN exec_str FLOAT DEFAULT NULL COMMENT '당일 마감 체결강도(%) — ka10047',
    ADD COLUMN exec_str_5d FLOAT DEFAULT NULL COMMENT '체결강도 5일 평균(%)';

-- 시장 분위기: 시간외단일가 등락률 순위(ka10098, ETF·ETN 제외) 상·하위 스캔에서
-- ±3% 이상 급등/급락 종목 수를 굽는다 — 시간외 시장 반응의 강도 게이지.
ALTER TABLE market_snapshot
    ADD COLUMN ah_up3_cnt INT DEFAULT NULL COMMENT '시간외단일가 +3% 이상 종목 수(ka10098)',
    ADD COLUMN ah_dn3_cnt INT DEFAULT NULL COMMENT '시간외단일가 -3% 이하 종목 수(ka10098)';
