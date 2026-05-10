-- ============================================================
-- 키움 액세스 토큰 단일행 보관 테이블
-- 매일 07:00 KST 갱신, 모든 워커가 ensure_token()으로 공유
-- ============================================================
CREATE TABLE IF NOT EXISTS kiwoom_token (
    id           INT PRIMARY KEY DEFAULT 1,
    access_token VARCHAR(512) NOT NULL,
    expires_dt   VARCHAR(20),                            -- 키움 응답 expires_dt (YYYYMMDDHHMMSS)
    issued_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- content_analysis: 언급 종목별 섹터 매핑 컬럼
-- related_tickers와 1:1 대응 [{"ticker":"...","sector":"..."}]
-- ============================================================
ALTER TABLE content_analysis
    ADD COLUMN ticker_sectors VARCHAR(500) DEFAULT NULL
    COMMENT 'related_tickers와 1:1 대응 [{"ticker":"...","sector":"..."}]';

-- ============================================================
-- ticker_dictionary: 섹터 캐시 컬럼 추가 (TTL 30일)
-- ============================================================
ALTER TABLE ticker_dictionary
    ADD COLUMN sector VARCHAR(100) DEFAULT NULL,
    ADD COLUMN sector_updated_at TIMESTAMP NULL DEFAULT NULL;
