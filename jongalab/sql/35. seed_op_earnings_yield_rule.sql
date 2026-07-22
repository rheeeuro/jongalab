-- 영업이익 이익수익률 가설 시드 (2026-07-22, 사용자 통설: "영업이익이 시총 1/10은 돼야")
--
-- 통설: "대부분 (좋은 종목은) 영업이익이 그래도 시가총액의 1/10은 돼야 한다".
-- = op_earnings_yield(영업이익÷시총, sql/34 파생) >= 0.1 (주가/영업이익 10배 이하).
-- 흑자·저평가라는 '재무 체력' 필터. 종가베팅(오버나이트)에서 이 저속 팩터가 익일
-- 수익률을 실제로 끌어올리는지는 미검증 — candidate 로 등록해 rule_evaluator 가 표본을
-- 쌓고 대조군(control) 대비 우위를 판정한 뒤에만 승격한다. 점수·선정 무영향.
--
-- 설계 메모:
--   · role=selector — 사용자 표현("종목 선정 기준")대로 '조건 통과 종목을 고르는' 가설.
--     승격 시 hybrid/rules 모드에서 매수 후보 선정에 참여(현행 legacy 모드에선 무영향).
--   · predicate 는 컬럼-상수만 되므로 비율을 op_earnings_yield 파생 컬럼으로 미리 구웠다
--     (edge_features.op_earnings_yield, closing_bet 선정 시점). SELECTION_TIME_COLS 포함 →
--     승격 시 선정 시점 실제 실행 가능.
--   · 결측(적자·신규상장·시총 결측 → op_earnings_yield NULL)은 매칭 실패로 자연 제외(보수적).
--   · 저빈도 가능성 — 모멘텀 유니버스엔 고멀티플 성장주가 많아 10% 이익수익률을 넘는 종목이
--     소수일 수 있다. min_sample 40 도달까지 수개월 걸릴 수 있으며, out-of-sample 로 판정한다.
--   · family=f8_value — 재무·가치 축(신설). 밸류에이션(fin_per/pbr)·수익성(fin_roe) 후속
--     가설도 이 family 로 묶인다.

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('f8_op_earnings_yield', '영업이익 시총 1/10', 'f8_value', 'selector',
 '기업 재무 체력 필터: 최근 영업이익이 시가총액의 1/10 이상(영업이익÷시총 ≥ 0.1, 곧 주가가 영업이익의 10배 이하)인 종목만 고른다. 흑자이면서 이익 대비 지나치게 비싸지 않은 종목이라는 가치 가설이다. 다만 종가베팅은 하루짜리 오버나이트 전략이라, 분기 단위로 천천히 바뀌는 이런 재무 지표가 익일 수익률을 실제로 끌어올리는지는 아직 검증되지 않았다 — 그래서 실매매(live)가 아닌 관찰(candidate) 상태로 등록해 성적표를 모으는 중이다. 참고: 급등 모멘텀 종목엔 이익 대비 비싼 성장주가 많아 이 기준을 넘는 종목은 소수일 수 있다.',
 '[{"col":"op_earnings_yield","op":">=","value":0.1}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
