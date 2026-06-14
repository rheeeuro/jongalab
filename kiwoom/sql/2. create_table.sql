-- ============================================================
-- 키움 액세스 토큰 단일행 보관 테이블
-- 매일 07:00 KST 갱신, 키움 데이터 서버 워커가 ensure_token()으로 공유
-- 전용 kiwoom DB 에 보관 (jongalab 과 동일 MariaDB 서버, 별도 스키마)
-- ============================================================
CREATE TABLE IF NOT EXISTS kiwoom_token (
    id           INT PRIMARY KEY DEFAULT 1,
    access_token VARCHAR(512) NOT NULL,
    expires_dt   VARCHAR(20),                            -- 키움 응답 expires_dt (YYYYMMDDHHMMSS)
    issued_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
