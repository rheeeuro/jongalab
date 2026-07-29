-- 뉴스 '재료 지속성' 라벨 (2026-07-29)
-- 목적: 종가베팅 가설 "수치가 이미 확정된 단발 이벤트는 종가에 소진되고, 다음 마일스톤이 남은
--       연속 재료는 익일까지 이어진다" 를 측정한다. 전부 점수 무영향(적재 전용).
--
-- 배경: 기존 뉴스 라벨은 두 가지 문제로 검증이 불가능했다.
--   ① 커버리지 — LLM 라벨(news_sentiment/news_catalyst)이 Ollama 처리량 때문에 하루 최대 5행
--      (closing_bet 의 MAX_NEWS_SUMMARIES). 실측 4주간 46행/12거래일로 표본이 안 쌓였다.
--      → OpenAI 벌크 판정(core/news_material_judge)으로 뉴스 있는 유니버스 전건(≈16행/일)으로 확대.
--   ② 축 — '언급의 지속'(news_prior_avg 등 카운트 기반)은 재보니 시총 프록시였다(대형주는 매일
--      아침 기사가 난다). 재료 자체의 지속성은 DB 에 프록시가 없어 헤드라인 텍스트를 읽어야 나온다.
--
-- '지속성 점수' 한 개를 LLM 에 묻지 않는다 — 감(感)이면 오탐 육안 감사가 불가능하다.
-- 관측 가능한 사실 4축(next_milestone/amount_locked/driver_scope/stage)을 묻고,
-- 등급(news_durability)은 코드가 결정론적으로 합성한다(derive_durability). 합성 규칙을 바꿔도
-- 4축이 남아 있으면 과거 라벨을 재해석할 수 있다.
--
-- 채점(news_followup_days)은 outcome_backfill 이 채운다: 리포트일 +1~+N일 사이에 **시세보도를
-- 제외한** 언급이 있던 날짜 수. 시세보도를 빼는 이유는 역인과다 — 갭상승이 "XX 급등" 기사를
-- 만들므로(실측 21%) 그걸 후속 재료로 세면 "재료가 이어졌다"가 "어제 올랐다"의 동어반복이 된다.
-- 이진(있음/없음)이 아니라 일수인 이유: 10일 창이면 대형주는 거의 100%가 '있음'이라 이진 라벨이
-- 또 시총 더미가 된다.
-- ⚠️ 일수로 세도 시총 부하는 남는다(2026-07-20 실측: 현대차·SK하이닉스 9일 vs 소형주 0일).
--    그래서 이 값은 **라벨 채점 전용**이고 종목 간 직접 비교에 쓰면 안 된다 — 분석 때는
--    그 종목 자신의 사전 기저(news_prior_avg = 직전 7일 일평균)나 시총 버킷 대비로 정규화하라.
--    수익 채점(next_open_ret)과 라벨 채점(이 컬럼)을 섞지 말 것: 라벨이 맞았는데 수익이 없으면
--    축이 죽은 것이고, 라벨이 틀렸으면 프롬프트 문제다(처방이 정반대).

ALTER TABLE daily_stock_report
    ADD COLUMN news_next_milestone TINYINT(1) DEFAULT NULL
        COMMENT 'LLM: 재료에 남은 다음 예정 사건이 있는가(1/0, NULL=미판정)' AFTER news_catalyst,
    ADD COLUMN news_amount_locked TINYINT(1) DEFAULT NULL
        COMMENT 'LLM: 재료 수치가 이미 확정·소진됐는가(1/0, NULL=미판정)' AFTER news_next_milestone,
    ADD COLUMN news_driver_scope VARCHAR(12) DEFAULT NULL
        COMMENT 'LLM: 재료 동인 범위(종목단독/산업사이클/불명)' AFTER news_amount_locked,
    ADD COLUMN news_stage VARCHAR(12) DEFAULT NULL
        COMMENT 'LLM: 재료 사이클 국면(첫발표/진행/마무리/불명)' AFTER news_driver_scope,
    ADD COLUMN news_durability VARCHAR(6) DEFAULT NULL
        COMMENT '파생: 재료 지속성 등급(연속/중립/소진) — 4축에서 derive_durability 로 합성' AFTER news_stage,
    ADD COLUMN news_label_reason VARCHAR(255) DEFAULT NULL
        COMMENT 'LLM 지속성 판정 근거 한 문장(육안 감사용)' AFTER news_durability,
    ADD COLUMN news_judge_max_at DATETIME DEFAULT NULL
        COMMENT '판정에 반영된 마지막 news_mention.created_at — 30분 재실행 시 재호출 스킵 기준' AFTER news_label_reason,
    ADD COLUMN news_followup_days TINYINT DEFAULT NULL
        COMMENT '채점: 리포트일 +1~+N일 중 시세보도 제외 언급이 있던 날짜 수(outcome_backfill)' AFTER news_judge_max_at;
