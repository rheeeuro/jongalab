-- 매물대(볼륨프로파일) 피처 선축적 (2026-07-19, 매물대 PDF 검토 후속 — 컬럼만, rule 없음)
--
-- 배경: 가격 레벨 축(전고점·라운드피겨, sql/20·22)은 레벨의 '위치'만 본다 — 그 고점이
-- 스파이크로 스친 얇은 고점인지 수개월 횡보로 다져진 두터운 벽("교통체증 구간")인지
-- 구분하지 못한다. 이 마이그레이션은 '두터움(거래량 가중)'을 캡처한다.
-- 추가 API 콜 0 — closing_bet 이 이미 받는 일봉(ka10081) 250봉의 고가·저가·거래량을
-- 저가~고가 균등 배분하는 일봉 근사 볼륨프로파일(core.edge_features 순수 함수).
--
--   overhead_vol_ratio — 직전 250거래일(당일 포함) 거래량 중 현재가 '위' 가격대 비중(0~1).
--                        0 근처 = 머리 위 매물 없음(신고가 논리의 정량판), 클수록 물린
--                        물량(본전 매도 압력)이 두텁다.
--   poc_dist_pct       — 최대 거래 집중 가격대(POC) 대비 현재가 거리(%).
--                        양수=매물대 위(하락 시 지지 후보), 음수=아래(상승 시 저항 후보).
--
-- ★ rule 은 의도적으로 등록하지 않는다: 같은 '가격 레벨 저항' 축의 rule 이 이미 5종
--   (veto_prior_high_wall/veto_round_figure_cap/f5_prior_high_break/f5_round_figure_break/
--   f5_breakout_structure) 미검증 상태로 판정(8월 초~중순) 대기 중이다. 표본 축적은 달력
--   시간이 자산이라 피처만 먼저 굽고, 레벨 축 판정 결과를 보고 '두터움'을 조건부로 결합한
--   rule(예: 벽이 두터울 때만 veto)을 그때 등록한다.

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS overhead_vol_ratio FLOAT DEFAULT NULL
        COMMENT '250일 거래량 중 현재가 위 비중(0~1, 매물대 두터움) — core.edge_features.overhead_vol_ratio' AFTER red_candle_streak,
    ADD COLUMN IF NOT EXISTS poc_dist_pct FLOAT DEFAULT NULL
        COMMENT '최대 거래 집중 가격대(POC) 대비 현재가 거리(%) — core.edge_features.poc_dist_pct' AFTER overhead_vol_ratio;
