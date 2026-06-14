CREATE TABLE IF NOT EXISTS channels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL,
    channel_id VARCHAR(50) NOT NULL UNIQUE, -- 유튜브 채널 고유 ID
    is_active BOOLEAN DEFAULT TRUE,         -- 모니터링 활성화 여부 (ON/OFF)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL UNIQUE, -- 유튜브ID or 텔레그램Link
    source_name VARCHAR(100),                 -- 채널명
    title VARCHAR(255),                       -- 영상제목 or 메시지요약
    analysis_content TEXT,                    -- AI 분석 결과
    sentiment_score INT DEFAULT 50,           -- 감성 점수 (0~100, 기본 50=중립)
    platform VARCHAR(20) DEFAULT 'youtube',   -- 'youtube', 'telegram', 'news'
    source_url VARCHAR(255),                  -- 원문 링크
    related_tickers VARCHAR(255) DEFAULT NULL, -- JSON 배열 [{"ticker":"...", "name":"..."}]
    ticker_sectors VARCHAR(500) DEFAULT NULL COMMENT 'related_tickers와 1:1 대응 [{"ticker":"...","sector":"..."}]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_external_id (external_id)
);

CREATE TABLE IF NOT EXISTS daily_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_date DATE NOT NULL,
    buy_stock VARCHAR(100),
    buy_ticker VARCHAR(20),
    buy_reason TEXT,
    sell_stock VARCHAR(100),
    sell_ticker VARCHAR(20),
    sell_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telegram_channels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    channel_identifier VARCHAR(100) NOT NULL COMMENT '채널 username(문자) 또는 ID(숫자)',
    display_name VARCHAR(100) COMMENT '대시보드에 표시할 이름',
    is_active BOOLEAN DEFAULT TRUE COMMENT '1: 수집중, 0: 중지',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 1. 통합 소스 테이블 생성
CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    platform VARCHAR(20) NOT NULL, -- 'youtube', 'telegram' 등
    identifier VARCHAR(100) NOT NULL, -- 채널ID, Username 등
    name VARCHAR(100), -- 표시할 이름 (슈카월드, 등)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ticker_dictionary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(100) UNIQUE NOT NULL,
    ticker_symbol VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING',  -- 'PENDING'(대기중), 'ACTIVE'(검증완료), 'INACTIVE'(비활성)
    sector VARCHAR(100) DEFAULT NULL,            -- 섹터 캐시 (TTL 1년 — 형식적 방어선, 실제로는 거의 고정값)
    sector_updated_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 종목일간리포트 테이블 생성
-- Phase 2 수급 분석 결과를 일별로 저장
CREATE TABLE IF NOT EXISTS daily_stock_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_date DATE NOT NULL,
    stock_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100) NOT NULL,
    sector VARCHAR(50) DEFAULT '기타',
    current_price INT DEFAULT 0,
    change_pct FLOAT DEFAULT 0.0,
    trading_value BIGINT DEFAULT 0,
    market_cap BIGINT DEFAULT 0,

    -- 수급 관련
    supply_score FLOAT DEFAULT 0.0,   -- 최근 5일 수급 정밀 점수 (0~100). 등급(S/A/B/C/D)은 응답 시점에 점수에서 파생
    inst_net_buy BIGINT DEFAULT 0,
    frgn_net_buy BIGINT DEFAULT 0,
    indv_net_buy BIGINT DEFAULT 0,
    prog_net_buy BIGINT DEFAULT 0,
    supply_days INT DEFAULT 0,
    supply_history JSON DEFAULT NULL,    -- 최근 5일 수급 현황 (투자자별 순매수)

    -- 차트 분석
    ma_aligned TINYINT(1) DEFAULT 0,
    near_high TINYINT(1) DEFAULT 0,
    hourly_candles JSON DEFAULT NULL,       -- 1시간봉 캔들 데이터 (1주일치)

    -- 대장주 / 테마주 / 점수
    is_leader TINYINT(1) DEFAULT 0,
    is_theme_stock TINYINT(1) DEFAULT 0,
    content_score FLOAT DEFAULT 0.0,
    score FLOAT DEFAULT 0.0,
    rank_no INT DEFAULT 0,

    -- 갭 체크(다음날 아침) 결과 영구 보존: 08:10 NXT, 09:10 KRX 재조회 결과를 Top 10 종목에 업데이트
    gap_nxt_price INT DEFAULT NULL COMMENT '갭 체크 NXT 가격(08:10)',
    gap_nxt_pct FLOAT DEFAULT NULL COMMENT '리포트가 → NXT 등락률(%)',
    gap_krx_price INT DEFAULT NULL COMMENT '갭 체크 KRX 가격(09:10)',
    gap_krx_pct FLOAT DEFAULT NULL COMMENT '리포트가 → KRX 등락률(%)',
    gap_checked_at TIMESTAMP NULL DEFAULT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_date_code (report_date, stock_code),
    INDEX idx_report_date (report_date),
    INDEX idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 전략 설정 (단일 행, JSON으로 관리)
CREATE TABLE IF NOT EXISTS strategy_config (
    id INT PRIMARY KEY DEFAULT 1,
    config JSON NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS daily_sector_report (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    report_date    DATE NOT NULL,
    thema_grp_cd   VARCHAR(20) NOT NULL,
    thema_nm       VARCHAR(50) NOT NULL,
    stk_num        INT DEFAULT 0,
    flu_rt         FLOAT DEFAULT 0.0,
    dt_prft_rt     FLOAT DEFAULT 0.0,
    main_stk       VARCHAR(50),
    rising_stk_num INT DEFAULT 0,
    fall_stk_num   INT DEFAULT 0,
    rank_no        INT DEFAULT 0,
    stocks         JSON,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date_thema (report_date, thema_grp_cd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 텔레그램 전송 대상 유저 (id = 텔레그램 chat id)
CREATE TABLE IF NOT EXISTS telegram_users (
    id         VARCHAR(50) PRIMARY KEY,               -- 텔레그램 chat id
    name       VARCHAR(50) NOT NULL,                  -- 표시용 이름 (CHAT_ID, CHAT_ID2 등)
    role       VARCHAR(10) NOT NULL DEFAULT 'NORMAL', -- 'ADMIN', 'NORMAL'
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
