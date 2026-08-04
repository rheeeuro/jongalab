-- ============================================================
-- 증권 섹션 뉴스 원자료 (2026-08-05) — **표시 전용 계층**
--
-- [왜 새 테이블인가]
--   뉴스 탭 헤드라인 스트림이 `news_mention`(텔레그램 종합 속보 채널)을 읽는데, 그 채널은
--   주식 전용이 아니라 **종합 속보**다. 저장 여부를 `news_matcher` 사명 매칭 하나로만
--   가르다 보니 주식과 무관한 기사가 그대로 화면에 올라왔다 — 2026-08-05 실측 14일
--   5,674기사 중 명백한 오탐 4.1%:
--     · 일반명사와 같은 사명 — 남성(004270) `70대 남성 사망` · 대상(001680) `수사 대상
--       암호화폐 탈취` · 상보(027580) `7월 소비자물가 2.8%↑(상보)` · 서한(011370)
--       `애플에 "중국 메모리 쓰지마" 서한` · 진도(088790) `日 구마모토 진도 7.1 강진`
--     · KBO 구단명 = 모기업 사명 — `한화, 삼성 4-1 제압 3연패 탈출`(한화 000880)
--   매처를 고쳐도 이건 못 막는다. **모집단 자체가 종합 뉴스**이기 때문이다.
--   네이버 증권 섹션 목록은 모집단이 이미 증권 기사라 야구·사건사고·연예가 구조적으로
--   들어오지 않는다 → 화면 소스를 통째로 갈아끼운다.
--
-- [왜 news_mention 에 넣지 않는가]
--   ① `ticker NOT NULL` + `UNIQUE(source_url, ticker)` 구조라 **종목이 안 붙는 기사**
--      (시황·환율·채권 — 증권 뉴스의 절반)를 넣을 자리가 없다. 센티넬 ticker 를 만들면
--      모든 종목별 집계가 그 값을 평생 피해 다녀야 한다.
--   ② news_mention 은 **집계 원자료**다. `news_count`/`news_unique_count` 가 rule 3종의
--      입력이고 그중 `veto_bad_news` 는 live(자금 경로)다. 표시용 행을 같은 테이블에
--      섞으면 `config.NEWS_ACTIVE_SOURCES` 게이트(sql/44)가 지키려던 성질이 조용히
--      깨진다 — 새 조회 함수가 소스 필터를 한 번만 빠뜨려도 실탄 입력이 바뀐다.
--   그래서 **표시 계층과 집계 계층을 테이블로 분리**한다. 이 테이블은 화면만 읽고,
--   라벨·rule·veto·점수는 절대 읽지 않는다.
--
-- [왜 기사 1행인가]
--   news_mention 은 '헤드라인 × 언급 종목' 1행이라 스트림이 파이썬에서 다시 접어야 했다
--   (`get_news_stream` 의 2단 조회). 화면이 원하는 단위가 애초에 기사이므로 그대로 저장하고
--   종목 칩은 `tickers` JSON 에 담는다. 페이징이 SQL 한 번으로 정확해진다.
--
-- [tickers 가 JSON 인 이유] 조인해서 얻을 게 없다 — 칩은 표시 전용이고 이 테이블로
--   종목별 조회를 하지 않는다(그건 news_mention 의 일이다). 종목 축 질의가 필요해지는
--   순간은 이 계층이 집계로 승격되는 때이고, 그때는 news_mention 쪽을 쓰는 게 맞다.
--
-- [보존] cleanup_content 가 NEWS_RETENTION_DAYS(30) 이전 행을 삭제한다. 화면 날짜 이동이
--   최근 60영업일까지 가능하지만 그건 리포트 날짜 목록이고, 헤드라인은 없으면 빈 목록으로
--   자연 degrade 한다(집계에 안 쓰이므로 표본이 잘릴 걱정이 없다).
-- ============================================================

CREATE TABLE IF NOT EXISTS sec_news (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_key VARCHAR(40) NOT NULL
        COMMENT '네이버 officeId/articleId — 재수집 멱등키(URL 형식이 바뀌어도 안 흔들린다)',
    headline VARCHAR(500) NOT NULL COMMENT '기사 제목(목록 title 속성 — 전체 제목)',
    source_url VARCHAR(500) NOT NULL COMMENT '기사 원문 뷰어 URL',
    press VARCHAR(100) DEFAULT NULL COMMENT '언론사명',
    published_at DATETIME NOT NULL COMMENT '발행 시각(분 단위) — 스트림 정렬·날짜 기준',
    tickers JSON DEFAULT NULL
        COMMENT '사명 매칭 결과 [{"ticker","name"}] — 화면 종목 칩 전용, 집계에 쓰지 않는다',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '수집 시각(운영 감사용)',
    UNIQUE KEY uq_article_key (article_key),
    INDEX idx_published (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='네이버 증권 섹션 기사 원자료 — 뉴스 탭 표시 전용(집계·rule·veto 무관)';
