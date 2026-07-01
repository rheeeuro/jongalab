-- content_analysis 구조화 요약 필드 추가 (B+C 고도화)
-- tldr(한 줄 요약) / tags(테마 해시태그) / stock_calls(종목별 방향·확신·시간축)
-- 기존 행은 NULL 로 남고 신규 수집분부터 채워진다. 반복 실행 안전(IF NOT EXISTS).
ALTER TABLE content_analysis
    ADD COLUMN IF NOT EXISTS tldr VARCHAR(255) DEFAULT NULL COMMENT '한 줄 대표 요약(카드 헤드라인)',
    ADD COLUMN IF NOT EXISTS tags JSON DEFAULT NULL COMMENT '테마 해시태그 배열 ["#반도체", ...]',
    ADD COLUMN IF NOT EXISTS stock_calls JSON DEFAULT NULL COMMENT '종목별 판단 [{"name","ticker","stance","conviction","horizon","reason"}]';
