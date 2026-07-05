-- 엣지 피처 스냅샷 확장 2차 — F5 수급 구조형 + F4 테마 후발 (2026-07-05)
-- 목적: 키움 API 로 이미 조회 중인 응답에서 버려지던 피처를 컬럼으로 굽는다(추가 API 콜은
--       vol_ratio 용 일봉 1콜/종목뿐). 전부 선정 시점(closing_bet 13~15시) 수집이라
--       SELECTION_TIME_COLS 자격이 있고, 매매 행위 영향 0 — 순수 관측·기록 레이어.
--
--   foreign_brokers_buying — 거래원(ka10002) 상위 5 매수창구 중 외국계 2곳 이상
--                            (trading_engine.analyze_supply_demand 가 이미 계산, 저장만 안 하던 값)
--   afternoon_ret          — 당일 13:00 시간봉 시가 → 선정 시점 현재가 등락률(%) (ka10080, 기수집)
--   vol_ratio              — 당일 거래량 ÷ 직전 20거래일 평균 거래량 (ka10081)
--   prog_buy_days          — 최근 5일 중 프로그램 순매수일 수 (ka90013, 기수집 supply_history 파생)
--   first_seen             — 직전 14일 daily_stock_report 유니버스에 없던 첫 등장 (DB 파생)
--   theme_strength         — 소속 테마(ka90001)의 당일 등락률 최대값(%) (비테마 NULL)
--   frgn_exhaust_rate      — 외인소진율(%) (ka10001 for_exh_rt, 기수집 응답에서 캡처)
--   frgn_exhaust_chg       — 직전 리포트 거래일 대비 외인소진율 변화(%p) (DB 파생)

ALTER TABLE daily_stock_report
    ADD COLUMN foreign_brokers_buying TINYINT(1) DEFAULT NULL COMMENT '외국계 거래원 매수창구 2곳 이상(ka10002)' AFTER sector_leader_chg,
    ADD COLUMN afternoon_ret FLOAT DEFAULT NULL COMMENT '당일 13시 시가 → 선정 시점 현재가 등락률(%)' AFTER foreign_brokers_buying,
    ADD COLUMN vol_ratio FLOAT DEFAULT NULL COMMENT '당일 거래량 ÷ 직전 20일 평균 거래량' AFTER afternoon_ret,
    ADD COLUMN prog_buy_days TINYINT DEFAULT NULL COMMENT '최근 5일 중 프로그램 순매수일 수' AFTER vol_ratio,
    ADD COLUMN first_seen TINYINT(1) DEFAULT NULL COMMENT '직전 14일 유니버스에 없던 첫 등장' AFTER prog_buy_days,
    ADD COLUMN theme_strength FLOAT DEFAULT NULL COMMENT '소속 테마 당일 등락률 최대(%) — 비테마 NULL' AFTER first_seen,
    ADD COLUMN frgn_exhaust_rate FLOAT DEFAULT NULL COMMENT '외인소진율(%) — ka10001 for_exh_rt' AFTER theme_strength,
    ADD COLUMN frgn_exhaust_chg FLOAT DEFAULT NULL COMMENT '직전 리포트 거래일 대비 외인소진율 변화(%p)' AFTER frgn_exhaust_rate;
