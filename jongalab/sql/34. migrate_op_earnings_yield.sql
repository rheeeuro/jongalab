-- 영업이익 이익수익률 파생 컬럼 (2026-07-22, 사용자 통설: "영업이익이 시총 1/10은 돼야")
--
-- 배경: sql/32 가 fin_op_profit(영업이익, 억원)·market_cap(시총, 원)을 각각 저장한다.
-- 사용자 통설 "대부분 영업이익이 시가총액의 1/10은 돼야 한다"는 곧 영업이익÷시총 ≥ 0.1
-- (≈ 주가/영업이익 10배 이하)이라는 가치·품질 필터다. 문제는 edge_predicate DSL 이
-- 컬럼-상수 비교만 지원하고 컬럼-컬럼(op_profit vs market_cap/10) 비율은 못 쓴다는 것.
-- → edge_predicate 규율("교차 컬럼 계산은 스냅샷 시점 파생 컬럼으로 구워 predicate 를
--    행 단위로 유지")대로, closing_bet 선정 시점에 비율을 미리 구워 이 컬럼에 저장한다.
--
-- 값(core.edge_features.op_earnings_yield): fin_op_profit(억원)*1e8 / market_cap(원).
--   0.1 = 영업이익이 시총의 1/10, 적자면 음수, 시총 결측/0 이하·영업이익 결측이면 NULL.
--   추가 API 콜 0(이미 있는 두 값의 파생). 분기 저속 데이터·점수 무영향.
--
-- rule: candidate 로만 등록(sql/35) — 선정/점수 무영향. 종가베팅(오버나이트)에서 저속
--   재무 필터가 유효한지 미검증이므로 백테스트(rule_evaluator)로 표본 축적 후 판정한다.
--   선정 시점 파생 컬럼이므로 core.edge_policy.SELECTION_TIME_COLS 에 포함(향후 live 자격).

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS op_earnings_yield FLOAT DEFAULT NULL
        COMMENT '영업이익÷시가총액(파생) — 0.1=영업이익이 시총 1/10, 적자면 음수 — core.edge_features.op_earnings_yield'
        AFTER fin_net_income;
