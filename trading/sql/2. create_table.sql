-- ============================================================
-- trading DB 스키마 — 자동매매 집행/포지션/리스크/감사
-- jongalab·kiwoom 과 동일 MariaDB 서버, 전용 trading 스키마
-- 첫 범위: 종가베팅 집행
-- ============================================================

USE trading;

-- 매수 시그널 큐 — jongalab(closing_bet)이 적재, trading 이 소비
-- (두 도메인의 유일한 결합점)
CREATE TABLE IF NOT EXISTS trade_signal (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    trade_date  CHAR(8) NOT NULL,                       -- YYYYMMDD
    stk_cd      VARCHAR(20) NOT NULL,
    stk_nm      VARCHAR(100),
    rank_no     INT,                                    -- 종가베팅 후보 순위
    score       DECIMAL(6,2),
    status      ENUM('pending','executing','done','rejected','expired') NOT NULL DEFAULT 'pending',
    note        VARCHAR(255),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_date_status (trade_date, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 주문 의도/전송 기록 (idempotency_key 로 중복 전송 차단)
CREATE TABLE IF NOT EXISTS `order` (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    signal_id       BIGINT,
    stk_cd          VARCHAR(20) NOT NULL,
    side            ENUM('buy','sell') NOT NULL,
    qty             INT NOT NULL,
    price           INT NOT NULL DEFAULT 0,             -- 0 = 시장가
    ord_type        ENUM('market','limit') NOT NULL DEFAULT 'market',
    mode            ENUM('paper','live') NOT NULL DEFAULT 'paper',
    status          ENUM('intended','sent','accepted','rejected','filled','canceled') NOT NULL DEFAULT 'intended',
    kiwoom_ord_no   VARCHAR(40),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_stk (stk_cd),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 체결 기록
CREATE TABLE IF NOT EXISTS fill (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id    BIGINT NOT NULL,
    stk_cd      VARCHAR(20) NOT NULL,
    qty         INT NOT NULL,
    price       INT NOT NULL,
    filled_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 보유 포지션 (종목당 1행)
CREATE TABLE IF NOT EXISTS position (
    stk_cd      VARCHAR(20) PRIMARY KEY,
    qty         INT NOT NULL DEFAULT 0,
    avg_price   INT NOT NULL DEFAULT 0,
    realized_pnl BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 일일 리스크 상태 (거래일당 1행) — 한도 소진·서킷브레이커 추적
CREATE TABLE IF NOT EXISTS risk_state (
    trade_date      CHAR(8) PRIMARY KEY,                -- YYYYMMDD
    orders_count    INT NOT NULL DEFAULT 0,
    realized_pnl    BIGINT NOT NULL DEFAULT 0,
    breaker_tripped BOOLEAN NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 전역 킬스위치 단일행 (id=1)
CREATE TABLE IF NOT EXISTS kill_switch (
    id          INT PRIMARY KEY DEFAULT 1,
    flag        BOOLEAN NOT NULL DEFAULT 0,
    reason      VARCHAR(255),
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 리스크 한도 설정 단일행 (id=1) — 대시보드에서 수정, RiskConfig 가 로드
-- config JSON: MAX_ORDERS_PER_DAY / MAX_NOTIONAL_PER_NAME / MAX_DAILY_LOSS / MAX_POSITIONS
CREATE TABLE IF NOT EXISTS risk_config (
    id          INT PRIMARY KEY DEFAULT 1,
    config      JSON NOT NULL,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 불변 감사로그 (append-only) — 주문 의도 + 키움 응답 원문
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    event       VARCHAR(40) NOT NULL,
    stk_cd      VARCHAR(20),
    payload     JSON,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event (event),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
