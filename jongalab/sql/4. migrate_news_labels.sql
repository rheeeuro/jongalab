-- 뉴스 재료 라벨 강화 (2026-07-03)
-- 목적: 엣지 연구용 뉴스 팩터 라벨 적재. 종합점수(SCORE_NEWS_BONUS=0)에는 무영향이며,
--       outcome_backfill 의 next_open_ret 과 조인해 "어떤 뉴스 신호가 익일 수익과 상관 있는지"
--       표본이 쌓인 뒤 백테스트로 검증하기 위한 저장 전용 컬럼이다.
-- 집계 라벨(closing_bet 이 news_mention 에서 계산):
--   news_unique_count — 헤드라인 정규화 dedup 고유 기사 수(채널 복제 제거)
--   news_pm_count     — 12시 이후 언급 수(종가베팅 신선도: 장중 늦게 터진 재료)
--   news_first_today  — 직전 14일(보존 주기) 내 언급 이력이 없는 첫 등장 여부
--   news_prior_avg    — 직전 7일 일평균 언급 수(서프라이즈 배수의 분모)
-- LLM 라벨(기존 배치 요약 프롬프트 확장 — 추가 LLM 호출 없음, 요약 후보만 채워짐):
--   news_sentiment    — 재료 방향 0~100 (기존에 생성되고 버려지던 값을 저장)
--   news_catalyst     — 재료 유형(실적/수주계약/임상승인/M&A/정책테마/증자감자/지분변동/기타)

ALTER TABLE daily_stock_report
    ADD COLUMN news_unique_count INT DEFAULT 0 COMMENT '당일 고유 기사 수(헤드라인 정규화 dedup)' AFTER news_count,
    ADD COLUMN news_pm_count INT DEFAULT 0 COMMENT '당일 12시 이후 언급 수(신선도)' AFTER news_unique_count,
    ADD COLUMN news_first_today TINYINT(1) DEFAULT 0 COMMENT '직전 14일 내 첫 언급 여부' AFTER news_pm_count,
    ADD COLUMN news_prior_avg FLOAT DEFAULT NULL COMMENT '직전 7일 일평균 언급 수(서프라이즈 분모)' AFTER news_first_today,
    ADD COLUMN news_sentiment TINYINT DEFAULT NULL COMMENT 'LLM 재료 방향 0~100(요약 후보만)' AFTER news_summary,
    ADD COLUMN news_catalyst VARCHAR(20) DEFAULT NULL COMMENT 'LLM 재료 유형(요약 후보만)' AFTER news_sentiment;
