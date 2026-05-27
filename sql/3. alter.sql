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
-- ticker_dictionary: 섹터 캐시 컬럼 추가 (TTL 1년 — 형식적 방어선, 실제로는 거의 고정값)
-- ============================================================
ALTER TABLE ticker_dictionary
    ADD COLUMN sector VARCHAR(100) DEFAULT NULL,
    ADD COLUMN sector_updated_at TIMESTAMP NULL DEFAULT NULL;

-- ============================================================
-- daily_stock_report: 갭 체크(다음날 아침) 결과 영구 보존
-- 08:10 NXT, 09:10 KRX 재조회 결과를 Top 10 종목에 업데이트
-- ============================================================
ALTER TABLE daily_stock_report
    ADD COLUMN gap_nxt_price INT DEFAULT NULL COMMENT '갭 체크 NXT 가격(08:10)',
    ADD COLUMN gap_nxt_pct FLOAT DEFAULT NULL COMMENT '리포트가 → NXT 등락률(%)',
    ADD COLUMN gap_krx_price INT DEFAULT NULL COMMENT '갭 체크 KRX 가격(09:10)',
    ADD COLUMN gap_krx_pct FLOAT DEFAULT NULL COMMENT '리포트가 → KRX 등락률(%)',
    ADD COLUMN gap_checked_at TIMESTAMP NULL DEFAULT NULL;
