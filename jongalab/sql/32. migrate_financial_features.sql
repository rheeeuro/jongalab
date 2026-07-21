-- 재무 스냅샷 피처 선축적 (2026-07-22, 실험실 검증 데이터에 기업 재무 추가 — 컬럼만, rule 없음)
--
-- 배경: 지금까지의 피처는 수급·차트·시간외 등 '단기 흐름' 축뿐이었다. 이 마이그레이션은
-- 기업의 '재무 체력' 축(밸류에이션·수익성·규모)을 유니버스 전체에 함께 저장한다.
-- 추가 API 콜 0 — closing_bet 이 선정 시점(13~15시) 후보마다 이미 호출하는 주식기본정보
-- (ka10001) 응답에 per/pbr/ev/roe/eps/bps/매출·영업이익·순이익이 실려온다(현재는 시가총액·
-- 외인소진율만 사용). core.edge_features.financials() 가 그 응답을 파싱한다.
--
--   fin_per / fin_pbr / fin_ev           — 밸류에이션(배)
--   fin_roe                              — 자기자본이익률(%)
--   fin_eps / fin_bps                    — 주당순이익·주당순자산(원)
--   fin_sales / fin_op_profit / fin_net_income — 매출액·영업이익·당기순이익(억원)
--
-- 특성: 분기 단위 저속 데이터라 매일 같은 값이 중복 저장될 수 있으나 연구용으로 무해하다.
--       결측(신규상장·적자 등 키움 공란)은 None → edge_predicate 가 매칭 실패로 처리(보수적).
--       ★ 부채비율은 ka10001 에 없어 제외 — 필요 시 별도 재무제표 TR 엔드포인트를 kiwoom
--         서버에 추가해야 한다.
--
-- ★ rule 은 의도적으로 등록하지 않는다(데이터부터 축적): 재무는 저속 팩터라 오버나이트
--   (종가베팅) 엣지에 직접 신호는 약하나, veto(적자·극단 고PER 제외)·품질 필터 축으로는
--   의미가 있을 수 있다. 표본이 쌓인 뒤(달력 시간) 어떤 축이 유효한지 보고 candidate rule 을
--   등록한다. 선정 시점 수집 컬럼이므로 core.edge_policy.SELECTION_TIME_COLS 에 이미 포함
--   시켰다(향후 rule 의 live 승격 실행 가능).

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS fin_per FLOAT DEFAULT NULL
        COMMENT 'PER(배) — ka10001 per' AFTER ma5_reclaim,
    ADD COLUMN IF NOT EXISTS fin_pbr FLOAT DEFAULT NULL
        COMMENT 'PBR(배) — ka10001 pbr' AFTER fin_per,
    ADD COLUMN IF NOT EXISTS fin_ev FLOAT DEFAULT NULL
        COMMENT 'EV/EBITDA(배) — ka10001 ev' AFTER fin_pbr,
    ADD COLUMN IF NOT EXISTS fin_roe FLOAT DEFAULT NULL
        COMMENT 'ROE(%) — ka10001 roe' AFTER fin_ev,
    ADD COLUMN IF NOT EXISTS fin_eps INT DEFAULT NULL
        COMMENT 'EPS 주당순이익(원) — ka10001 eps' AFTER fin_roe,
    ADD COLUMN IF NOT EXISTS fin_bps INT DEFAULT NULL
        COMMENT 'BPS 주당순자산(원) — ka10001 bps' AFTER fin_eps,
    ADD COLUMN IF NOT EXISTS fin_sales BIGINT DEFAULT NULL
        COMMENT '매출액(억원) — ka10001 sale_amt' AFTER fin_bps,
    ADD COLUMN IF NOT EXISTS fin_op_profit BIGINT DEFAULT NULL
        COMMENT '영업이익(억원) — ka10001 bus_pro' AFTER fin_sales,
    ADD COLUMN IF NOT EXISTS fin_net_income BIGINT DEFAULT NULL
        COMMENT '당기순이익(억원) — ka10001 cup_nga' AFTER fin_op_profit;
