-- ============================================================
-- news_mention 소스 구분 컬럼 (2026-07-31)
--
-- [왜] 뉴스 원자료 소스가 텔레그램 단일에서 네이버 증권(종목별 뉴스)까지 둘로 늘어난다.
--   유니버스 종목의 재료 라벨 커버리지가 47%(실측 18/38)뿐이고, 나머지 53%는 텔레그램
--   채널이 그 종목 기사를 안 옮겨서 생긴 공백이다. 네이버는 종목코드로 조회하므로
--   사명 사전매칭(no_match 55%)을 통째로 우회하고 커버리지가 92%로 올라간다(실측 35/38).
--
-- [왜 컬럼인가] channel_name LIKE '네이버%' 같은 문자열 판별은 운영자가 텔레그램 채널명을
--   바꾸는 순간 깨진다. stock_event.source 선례대로 명시 컬럼을 둔다.
--
-- [왜 게이트가 필요한가] 소스를 늘리면 집계 라벨이 도입일에 계단식으로 튄다 —
--   실측 네이버 당일 562행 vs 텔레그램 273행인데 **헤드라인 중복이 2%뿐**이라 상쇄 없이
--   3배 순증한다. news_unique_count 를 predicate 에 쓰는 rule 이 3종이고 그중
--   `veto_bad_news` 는 live(자금 경로)라, 검증 없이 유입시키면 실탄 변경이 된다.
--   그래서 config.NEWS_ACTIVE_SOURCES(기본 'telegram')가 repository 조회 전부를 필터하고,
--   네이버 행은 2~3주 관측 후 .env 한 줄로 승격한다.
--
-- [주의] 승격(2단계) 시 함께 해야 할 일 — 지금 하면 표본이 중간에 바뀌므로 미룬 항목들:
--   ① repository/news._normalize_headline 에 URL 제거 추가. 텔레그램 헤드라인 95%에 기사
--      URL 이 본문과 함께 저장돼 있어(제목+URL 한 컬럼), 네이버 행(제목만)과 정규화 키가
--      절대 일치하지 않는다 → 소스 간 채널 복제 제거가 작동하지 않는다. 지금 고치면
--      news_unique_count 가 흔들려 live veto 입력이 바뀐다.
--   ② 집계 라벨을 **고유 기사(source_url) 기준 + is_price_report 제외**로 전환. 네이버는
--      시황 기사 1건이 최대 16종목에 붙어(실측 행의 57%가 다종목 부착분) 행 카운트가
--      "그날 시황 기사 수"를 재게 되고, 대형주일수록 커져 또 시총 프록시가 된다.
--      실측 시세보도 비중: 행 기준 50% / 고유기사 기준 32%.
--   ③ 뉴스 라벨 기반 rule 재등록(registered_at 리셋 — 표본 성질이 바뀌므로).
--   ④ news_guard(자금 경로) 편입은 네이버 헤드라인 전건 육안 감사 후에만.
-- ============================================================

ALTER TABLE news_mention
    ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'telegram'
        COMMENT 'telegram | naver — 소비는 config.NEWS_ACTIVE_SOURCES 로 게이팅'
        AFTER company_name;

-- 소스 필터가 모든 조회에 붙으므로 기존 인덱스 선두에 얹지 않고 보조 인덱스로 둔다
-- (기존 idx_ticker_created / idx_created 는 그대로 쓰인다).
ALTER TABLE news_mention
    ADD INDEX idx_source_created (source, created_at);
