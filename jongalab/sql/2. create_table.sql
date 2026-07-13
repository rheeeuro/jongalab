CREATE TABLE IF NOT EXISTS channels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL,
    channel_id VARCHAR(50) NOT NULL UNIQUE, -- 유튜브 채널 고유 ID
    is_active BOOLEAN DEFAULT TRUE,         -- 모니터링 활성화 여부 (ON/OFF)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 보존 정책: created_at 3개월 이전 행은 cleanup_content 워커(매일 04:00)가 자동 삭제.
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
    tldr VARCHAR(255) DEFAULT NULL COMMENT '한 줄 대표 요약(카드 헤드라인)',
    tags JSON DEFAULT NULL COMMENT '테마 해시태그 배열 ["#반도체", ...]',
    stock_calls JSON DEFAULT NULL COMMENT '종목별 판단 [{"name","ticker","stance","conviction","horizon","reason"}]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_external_id (external_id)
);

-- 뉴스 속보 언급 (고빈도 뉴스 채널 전용, LLM 분석 없이 종목 사전매칭만).
-- content_analysis 와 분리 — 뉴스는 '재료 감지 신호'이지 '분석 콘텐츠'가 아니다.
-- 한 헤드라인이 여러 종목을 언급하면 종목당 1행. 보존 정책: cleanup_content 워커가 N일 이전 삭제.
CREATE TABLE IF NOT EXISTS news_mention (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,              -- 매칭된 종목코드 (6자리)
    company_name VARCHAR(100),                -- 매칭된 기업명
    headline VARCHAR(500),                    -- 뉴스 헤드라인(+링크 프리뷰)
    source_url VARCHAR(500),                  -- 원문/메시지 URL
    channel_name VARCHAR(100),                -- 뉴스 채널명
    published_at TIMESTAMP NULL DEFAULT NULL, -- 메시지 발행 시각(참고용)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 수집 시각(오늘 카운트 기준)
    UNIQUE KEY uq_url_ticker (source_url, ticker),   -- 동일 기사·종목 중복 방지
    INDEX idx_ticker_created (ticker, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
    -- 뉴스 재료 (news_mention 집계). news_count 는 종합점수 뉴스항(SCORE_NEWS_BONUS)의 입력이자
    -- 주간 가중치 튜너의 학습 피처. 기본 가중치 0이라 현재는 점수에 무영향(표시·튜닝 전용).
    -- news_unique_count 이하 라벨은 엣지 연구용(next_open_ret 조인 백테스트 대상, 점수 무영향).
    news_count INT DEFAULT 0,               -- 당일 뉴스 언급 건수
    news_unique_count INT DEFAULT 0,        -- 당일 고유 기사 수(헤드라인 정규화 dedup)
    news_pm_count INT DEFAULT 0,            -- 당일 12시 이후 언급 수(신선도)
    news_first_today TINYINT(1) DEFAULT 0,  -- 직전 14일 내 첫 언급 여부
    news_prior_avg FLOAT DEFAULT NULL,      -- 직전 7일 일평균 언급 수(서프라이즈 분모)
    news_summary TEXT DEFAULT NULL,         -- 후보 소수만 배치 LLM 재료 요약
    news_sentiment TINYINT DEFAULT NULL,    -- LLM 재료 방향 0~100(요약 후보만)
    news_catalyst VARCHAR(20) DEFAULT NULL, -- LLM 재료 유형(실적/수주계약/임상승인/M&A/정책테마/증자감자/지분변동/기타)
    news_headlines JSON DEFAULT NULL,       -- 최근 헤드라인 목록(표시용)
    score FLOAT DEFAULT 0.0,
    rank_no INT DEFAULT 0,

    -- 갭 체크(다음날 아침) 결과 영구 보존 — 실매매 청산 창과 동일 기준. 종목별로 venue 하나만 채워진다:
    --   NXT 상장 종목 → gap_nxt_*(전일 19:50 NXT → 당일 08:03 NXT)
    --   KRX 전용 종목 → gap_krx_*(전일 15:20 KRX → 당일 09:03 KRX)
    --   (2026-07-03 이전 행은 구 기준: 리포트가 → 08:10 NXT / 09:10 KRX, 두 컬럼 모두 존재 가능)
    gap_nxt_price INT DEFAULT NULL COMMENT '갭 체크 NXT 가격(08:03)',
    gap_nxt_pct FLOAT DEFAULT NULL COMMENT '전일 19:50 NXT → 08:03 NXT 등락률(%)',
    gap_krx_price INT DEFAULT NULL COMMENT '갭 체크 KRX 가격(09:03)',
    gap_krx_pct FLOAT DEFAULT NULL COMMENT '전일 15:20 KRX → 09:03 KRX 등락률(%)',
    gap_checked_at TIMESTAMP NULL DEFAULT NULL,
    exec_leg_ret FLOAT DEFAULT NULL COMMENT '실집행 청산창 등락률(%): NXT 19:50→08:03 / KRX 15:20→09:03',
    exec_leg_venue VARCHAR(3) DEFAULT NULL COMMENT 'exec_leg_ret 산출 venue: NXT 또는 KRX',

    -- 엣지 연구용: 상위 후보만이 아니라 Phase 2 통과 유니버스 전체를 저장한다.
    --   selected=1 은 실제 매매 핸드오프된 상위 종목(rank_no<=TRADED_TOP_N), 0 은 비선정 후보.
    --   next_open_ret 은 리포트일 종가 → '다음 거래일 시가' 등락률(%). selected 무관 전 종목 균일
    --   백필(outcome_backfill 워커, 수정주가 차트로 분할 상쇄). 선정/비선정을 가르는 요인 측정용 라벨.
    selected TINYINT(1) DEFAULT 1 COMMENT '실매매 핸드오프 종목(1) / 비선정 후보(0)',
    next_open_ret FLOAT DEFAULT NULL COMMENT '리포트일 종가 → 다음 거래일 시가 등락률(%), 백필',
    -- 결과 라벨 다중화 (Phase 2, 2026-07-04) — 앵커=KRX 확정 종가로 통일. 청산창 rule 비교용.
    --   일봉 백필 3종(outcome_backfill, 과거 소급 가능):
    next_high_ret FLOAT DEFAULT NULL COMMENT '종가→익일 고가 등락률(%) — 이론상 최대(VI/단일가 왜곡 유의)',
    next_low_ret FLOAT DEFAULT NULL COMMENT '종가→익일 저가 등락률(%) — 꼬리 리스크(스톱 관통 측정)',
    next_close_ret FLOAT DEFAULT NULL COMMENT '종가→익일 종가 등락률(%) — 홀드 시나리오',
    --   실시간 2종(gap_check --label-nxt 08:06, 유니버스 전체, 소급 불가):
    nxt_open_price INT DEFAULT NULL COMMENT '익일 08:06 NXT 가격(유니버스 전체)',
    nxt_open_ret FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가→익일 08:06 NXT 등락률(%) — 청산창 실측 우선 라벨',

    -- 엣지 피처 스냅샷 (Phase 1, 2026-07-04) — 관측·기록 전용, 점수 무영향.
    --   NXT 스냅샷(F3): gap_check --base-nxt(19:50)가 UPDATE. 종목당 KRX+NXT 2콜.
    krx_close_price INT DEFAULT NULL COMMENT '15:30 확정 종가(19:50 수집)',
    nxt_price_1950 INT DEFAULT NULL COMMENT '19:50 NXT 현재가(미상장/무거래 NULL)',
    nxt_gap_pct FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가 → 19:50 NXT 괴리율(%)',
    nxt_after_value BIGINT DEFAULT NULL COMMENT 'NXT 세션 누적 거래대금 근사(거래량×현재가)',
    nxt_listed TINYINT(1) DEFAULT NULL COMMENT '19:50 NXT 조회 성공 여부(NXT 상장 판별)',
    --   섹터 상대치(F4): closing_bet 저장 시점 유니버스 in-memory 파생(API 콜 없음).
    sector_rel_ret FLOAT DEFAULT NULL COMMENT '당일 등락률 − 동일 sector 평균 등락률(%p)',
    sector_leader_chg FLOAT DEFAULT NULL COMMENT '동일 sector 최고 등락률(%) — 후발주 판정 분모',
    --   수급 구조·테마 피처(F5·F4 2차, 2026-07-05): closing_bet 선정 시점(13~15시) 수집, 점수 무영향.
    foreign_brokers_buying TINYINT(1) DEFAULT NULL COMMENT '외국계 거래원 매수창구 2곳 이상(ka10002)',
    afternoon_ret FLOAT DEFAULT NULL COMMENT '당일 13시 시가 → 선정 시점 현재가 등락률(%)',
    vol_ratio FLOAT DEFAULT NULL COMMENT '당일 거래량 ÷ 직전 20일 평균 거래량',
    prog_buy_days TINYINT DEFAULT NULL COMMENT '최근 5일 중 프로그램 순매수일 수',
    first_seen TINYINT(1) DEFAULT NULL COMMENT '직전 14일 유니버스에 없던 첫 등장',
    theme_strength FLOAT DEFAULT NULL COMMENT '소속 테마 당일 등락률 최대(%) — 비테마 NULL',
    frgn_exhaust_rate FLOAT DEFAULT NULL COMMENT '외인소진율(%) — ka10001 for_exh_rt',
    frgn_exhaust_chg FLOAT DEFAULT NULL COMMENT '직전 리포트 거래일 대비 외인소진율 변화(%p)',
    is_bio TINYINT DEFAULT NULL COMMENT '바이오/제약 여부(선정 시점 파생 — core.edge_features.is_bio)',
    market VARCHAR(10) DEFAULT NULL COMMENT '시장 구분(코스피/코스닥 — ka10100 marketName, 거래소→코스피 정규화)',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_date_code (report_date, stock_code),
    INDEX idx_report_date (report_date),
    INDEX idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 시장 스냅샷 (일 단위 시장 피처, F2 해외 동조·레짐 연구용). gap_check --base-nxt(19:50)가 1행 upsert.
CREATE TABLE IF NOT EXISTS market_snapshot (
    snapshot_date   DATE PRIMARY KEY,
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    kospi_ret       FLOAT DEFAULT NULL,   -- 당일 코스피 등락률(%)
    kosdaq_ret      FLOAT DEFAULT NULL,   -- 당일 코스닥 등락률(%)
    nq_fut_ret      FLOAT DEFAULT NULL,   -- 나스닥100 선물(NQ=F) 등락률 — 19:50 시점
    spx_ret         FLOAT DEFAULT NULL,   -- S&P500 전일 종가 등락률
    sox_ret         FLOAT DEFAULT NULL,   -- 필라델피아 반도체(^SOX) 전일 등락률
    vix             FLOAT DEFAULT NULL,   -- VIX 지수 값(등락률 아님)
    usdkrw_ret      FLOAT DEFAULT NULL,   -- 원/달러 환율 등락률(%)
    k200f_day_ret   FLOAT DEFAULT NULL,   -- 코스피200 주간선물 등락률(장 마감 기준)
    k200f_night_ret FLOAT DEFAULT NULL    -- 야간선물 등락률(19:50 시점, kis_night_future)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 전략 설정 (단일 행, JSON으로 관리)
CREATE TABLE IF NOT EXISTS strategy_config (
    id INT PRIMARY KEY DEFAULT 1,
    config JSON NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 주간 매매성과 기반 가중치 튜닝 제안 (GPT 제안 → 수동 승인 후 strategy_config 반영)
CREATE TABLE IF NOT EXISTS weight_tuning_proposal (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    week_start         DATE NOT NULL,                       -- 분석 대상 주의 월요일
    week_end           DATE NOT NULL,                       -- 분석 대상 주의 금요일
    status             VARCHAR(10) NOT NULL DEFAULT 'pending', -- pending / approved / rejected
    sample_count       INT DEFAULT 0,                       -- 분석에 쓴 매매 종목 수
    winners_count      INT DEFAULT 0,
    losers_count       INT DEFAULT 0,
    total_realized_pnl BIGINT DEFAULT 0,                    -- 주간 실현손익 합(원)
    current_weights    JSON NOT NULL,                       -- 제안 시점의 종합점수 구성 가중치
    proposed_weights   JSON NOT NULL,                       -- GPT가 제안(+클램프)한 가중치
    rationale          TEXT,                                -- GPT 근거 설명
    dataset            JSON,                                -- winners/losers 지표 요약(감사·표시용)
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_at         TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uq_week (week_start),
    INDEX idx_status (status)
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

-- ============================================================
-- 한국투자증권(KIS) 액세스 토큰 단일행 보관 테이블 (id = 1)
-- 시장 탭 선물 시세 조회(core.kis_client)가 ensure_token()으로 공유.
-- 매일 1회 cron(jongalab-kis-token-refresh)으로 갱신, 만료 임박 시 on-demand 재발급.
-- ============================================================
CREATE TABLE IF NOT EXISTS kis_token (
    id           INT PRIMARY KEY DEFAULT 1,
    access_token VARCHAR(512) NOT NULL,
    expires_dt   VARCHAR(32),                            -- KIS access_token_token_expired (YYYY-MM-DD HH:MM:SS)
    issued_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 코스피200 야간선물 실시간 시세 단일행 (id = 1)
-- workers/kis_night_futures_ws.py 가 KIS WebSocket H0MFCNT0 체결 틱으로 갱신.
-- market_data 가 행의 신선도(updated_at)로 야간(WS) ↔ 주간(REST) 표시를 전환한다.
-- ============================================================
CREATE TABLE IF NOT EXISTS kis_night_future (
    id             INT PRIMARY KEY DEFAULT 1,
    symbol         VARCHAR(20),                            -- 근월물 단축코드 (예: A01609)
    price          DECIMAL(12,2),                          -- 야간 체결가
    change_val     DECIMAL(12,2),                          -- 전일대비 (부호 반영)
    change_percent DECIMAL(8,2),                           -- 전일대비율 (%)
    quote_time     VARCHAR(8),                             -- 체결 시각 HHMMSS
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Edge Ledger — 가설 원장 (Phase 3). rule_evaluator(09:40)가 매일 자동 채점.
--   edge_rule: 1행 = 반증가능한 가설 1개(predicate=조건 AND 결합, status candidate→live→retired).
--   edge_rule_daily: rule×날짜 평가 결과(스코어보드 시계열 + matched 감사 추적).
-- 상세는 core/edge_predicate.py(평가기)·workers/rule_evaluator.py·routers/edge_rule.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS edge_rule (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL UNIQUE,       -- 예: f3_nxt_gap_quality
    title         VARCHAR(80) DEFAULT NULL,          -- 카드 제목(한글) — NULL 이면 프론트가 name 폴백
    family        VARCHAR(20) NOT NULL,              -- 도메인: f1_news / f2_global / f3_nxt / f4_laggard / f5_supply / f6_ah / control
    role          VARCHAR(10) NOT NULL DEFAULT 'selector',  -- 역할: selector(선정) / veto(제외 전용) / benchmark(측정·기준선)
    description   VARCHAR(500) NOT NULL,             -- 인과 근거 필수: "누가 왜 내일 아침 사는가"
    predicate     JSON NOT NULL,                     -- 조건 목록(AND 결합, edge_predicate DSL)
    exit_label    VARCHAR(30) NOT NULL DEFAULT 'exec_leg_ret',  -- 채점에 쓸 결과 라벨 컬럼
    status        VARCHAR(10) NOT NULL DEFAULT 'candidate',      -- candidate / live / retired
    min_sample    INT NOT NULL DEFAULT 40,           -- 승격 심사 최소 표본(매칭 종목-일)
    registered_at DATE NOT NULL,                     -- ★ 사전 등록일 — 이 날짜 이후 표본만 승격 판정
    stats         JSON DEFAULT NULL,                 -- evaluator 캐시(n, mean_net, win_rate, std, ci_low, worst_low_ret, updated_through)
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    promoted_at   TIMESTAMP NULL DEFAULT NULL,
    retired_at    TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS edge_rule_daily (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id      INT NOT NULL,
    report_date  DATE NOT NULL,
    n_matched    INT NOT NULL DEFAULT 0,
    mean_net_ret FLOAT DEFAULT NULL,                 -- 매칭 종목 평균 (exit_label − EDGE_COST_PCT)
    matched      JSON DEFAULT NULL,                  -- [{code, name, ret, low}] 감사·복기용(ret=원본, 비용 미차감)
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_rule_date (rule_id, report_date),
    INDEX idx_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 통합 잡 스케줄러 실행 이력 (workers/scheduler.py)
-- 스케줄러가 잡을 spawn 할 때 running 행을 만들고, 종료 시 상태를 확정한다.
-- 관리자 페이지(워커 현황)와 실패 경보의 데이터 소스. 60일 지난 행은 자동 정리.
-- status: running / success / fail / timeout / aborted(스케줄러 재시작으로 유실)
-- ============================================================
CREATE TABLE IF NOT EXISTS job_run (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_name     VARCHAR(64) NOT NULL,
    scheduled_at DATETIME NOT NULL,
    started_at   DATETIME DEFAULT NULL,
    finished_at  DATETIME DEFAULT NULL,
    status       VARCHAR(10) NOT NULL DEFAULT 'running',
    exit_code    INT DEFAULT NULL,
    log_tail     TEXT DEFAULT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_job_time (job_name, scheduled_at),
    INDEX idx_time (scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
