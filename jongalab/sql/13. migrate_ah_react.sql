-- 시간외 초과반응 파생 컬럼 (2026-07-09)
-- ah_flu_rt(전일종가 대비)와 change_pct 의 차로 시간외 반응을 재려 했으나, 저녁 재실행의
-- change_pct 는 NXT 가격에 오염될 수 있다(17:50 이후 closing_bet 이 통합 시세로 갱신).
-- → after_hours_labels 워커가 KRX 확정 종가(수정주가 일봉 당일 캔들)를 앵커로 직접 계산해 굽는다.
--    ah_react = (시간외단일가 현재가 ÷ 당일 KRX 종가 − 1) × 100
-- edge_predicate 는 컬럼 간 비교를 지원하지 않으므로(절대 임계만) rule 이 쓰려면 파생 컬럼이 필요.

ALTER TABLE daily_stock_report
    ADD COLUMN ah_react FLOAT DEFAULT NULL COMMENT '시간외 초과반응(%) = 시간외단일가 ÷ 당일 KRX 종가 − 1';
