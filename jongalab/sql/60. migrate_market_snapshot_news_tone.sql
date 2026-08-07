-- 2026-08-07 market_snapshot 에 '매수 시점 뉴스 톤' 4컬럼 추가 (연구용 · 자금 경로 아님)
--
-- 배경: 시황을 재는 live 축이 선물·US 지표뿐이라, 관세·전쟁·해외 실적 같은 **뉴스 기반 시황**은
--   게이트에 전혀 반영되지 않는다. 원자료(sec_news 하루 ~1,000건, 종목 칩 없는 시황·정책 기사 64%)와
--   라벨(news_sector_label 의 scope='거시'/'섹터' + sentiment)은 이미 있는데 소비 경로가 없다.
--
-- 이 컬럼들은 그 축을 **검정 가능한 표본으로 만드는 것**이 목적이다 — daily_stock_report.next_open_ret
-- 와 조인해 "거시 뉴스가 부정적인 밤에 익일 성적이 나쁜가"의 부호·유의성을 먼저 확인한다.
-- ⛔ 검정 전 감액 승격 금지: 같은 계열 축인 macro_gate 의 VIX 프록시는 실측 부호가 설계와 **반대**였고
--    (2026-08-03: VIX 높을수록 익일 성적 좋음, corr +0.318/t=+2.87), WTI 축은 기각됐다.
--    근거는 docs/history/gates-sizing.md 참고.
--
-- 값의 시점 의미: gap_check --base-nxt(19:50 = NXT 매수 시점)가 채운다. 그 시각까지 라벨이 붙은
--   그날 기사만 집계하므로 **매수 시점에 알 수 있었던 값**이다(20:30 백로그 소화로 라벨이 더 붙어도
--   이 행은 갱신하지 않는다 — 사후 정보로 채우면 게이트 축 검정이 성립하지 않는다).
--   tone 은 sentiment 평균(0~100, 50=중립), cnt 는 그 평균의 표본 수. 라벨 0건이면 tone=NULL(=중립 아님).

ALTER TABLE market_snapshot
    ADD COLUMN news_macro_tone  FLOAT DEFAULT NULL
        COMMENT '매수시점(19:50)까지 라벨된 당일 거시 기사 sentiment 평균(0~100, 50=중립)',
    ADD COLUMN news_macro_cnt   INT   DEFAULT NULL
        COMMENT '위 평균의 표본 기사 수(0이면 tone NULL)',
    ADD COLUMN news_sector_tone FLOAT DEFAULT NULL
        COMMENT '매수시점까지 라벨된 당일 섹터 기사 sentiment 평균(0~100)',
    ADD COLUMN news_sector_cnt  INT   DEFAULT NULL
        COMMENT '위 평균의 표본 기사 수';
