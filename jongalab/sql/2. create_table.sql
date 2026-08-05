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
    related_tickers TEXT DEFAULT NULL, -- JSON 배열 [{"ticker":"...", "name":"..."}] (종목 다수 시 255 초과 → TEXT)
    ticker_sectors TEXT DEFAULT NULL COMMENT 'related_tickers와 1:1 대응 [{"ticker":"...","sector":"..."}]',
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
    body_preview VARCHAR(500) DEFAULT NULL,   -- 기사 리드문 발췌(네이버 종목별 경로만, sql/51)
    UNIQUE KEY uq_url_ticker (source_url, ticker),   -- 동일 기사·종목 중복 방지
    INDEX idx_ticker_created (ticker, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 사건 계층 — 종목×사건 1행(정규화, 영구 보존). news_mention(원자료, 14일)의 상위 계층.
-- 첫 소스는 DART 전자공시(workers/disclosure_collector, 평일 30분 주기). 상세는 sql/36.
CREATE TABLE IF NOT EXISTS stock_event (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker        VARCHAR(20)  NOT NULL,   -- 종목코드(6자리)
    event_date    DATE         NOT NULL,   -- 접수일(DART rcept_dt)
    source        VARCHAR(10)  NOT NULL,   -- dart (향후 news)
    source_key    VARCHAR(40)  NOT NULL,   -- DART 접수번호(rcept_no) — 멱등 수집 근거
    event_type    VARCHAR(24)  NOT NULL,   -- core.disclosure_events.classify 결과
    direction     TINYINT      NOT NULL DEFAULT 0,  -- +1 호재 / 0 중립 / -1 악재
    is_veto_type  TINYINT      NOT NULL DEFAULT 0,  -- 1 = 선정 제외 대상 악재
    is_correction TINYINT      NOT NULL DEFAULT 0,  -- 1 = 정정공시(veto 집계 제외)
    first_seen_at DATETIME     NOT NULL,   -- 수집기 최초 관측 시각(접수시각 근사)
    title         VARCHAR(255) NOT NULL,   -- report_nm 원문
    corp_name     VARCHAR(80)  DEFAULT NULL,
    raw_url       VARCHAR(255) DEFAULT NULL,
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_source_key (source, source_key),
    INDEX idx_ticker_date (ticker, event_date),
    INDEX idx_date_type (event_date, event_type)
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
    -- 재료 지속성 라벨 (sql/40, 축·합성 v2 = sql/52) — 뉴스 있는 유니버스 전건을 OpenAI 벌크
    -- 판정(news_material_judge). 사실 축은 LLM 이 내고 등급(news_durability)은 코드가 합성한다
    -- (derive_durability). 여기서 '지속성'은 언급의 지속이 아니라 **주가를 이어서 올려주는 성질**.
    news_next_milestone TINYINT(1) DEFAULT NULL, -- 남은 다음 예정 사건 있는가(NULL=미판정)
    news_milestone_horizon VARCHAR(10) DEFAULT NULL, -- 그 사건 시점: 1주내/1개월내/그이후/불명
    news_amount_locked TINYINT(1) DEFAULT NULL,  -- 재료 수치가 이미 확정·소진됐는가(실측 무차별 → 합성 제외)
    news_material_size_ratio DECIMAL(10,4) DEFAULT NULL, -- 재료 금액 ÷ 시가총액(LLM 추출 금액의 코드 파생)
    news_driver_scope VARCHAR(12) DEFAULT NULL,  -- 종목단독/산업사이클/불명
    news_stage VARCHAR(12) DEFAULT NULL,         -- 첫발표/진행/마무리/불명
    news_durability VARCHAR(6) DEFAULT NULL,     -- 파생 등급: 연속/중립/소진
    news_durability_v TINYINT DEFAULT NULL,      -- 합성 규칙 버전(현재 2) — v1/v2 표본 분리용
    news_material_age_h DECIMAL(5,1) DEFAULT NULL, -- 재료 신선도: 당일 최신 재료 기사 경과 시간(h, sql/56)
    news_label_reason VARCHAR(255) DEFAULT NULL, -- 지속성 판정 근거(육안 감사용)
    news_judge_max_at DATETIME DEFAULT NULL,     -- 판정 반영 마지막 언급 시각(30분 재실행 캐시 기준)
    news_followup_days TINYINT DEFAULT NULL,     -- 채점(참고값): +1~+N일 중 시세보도 제외 언급 날짜 수
    -- 재료 지속성 **가격 채점** (sql/53) — 라벨이 맞았는지 판정하는 주 정답지. 연구 전용.
    mat_run_ret_3d DECIMAL(8,3) DEFAULT NULL,    -- 익일 시가 → D+3 종가 등락률(%)
    mat_up_days TINYINT DEFAULT NULL,            -- D+1~D+3 중 상승 마감 일수(0~3)
    news_headlines JSON DEFAULT NULL,       -- 최근 헤드라인 목록(표시용)
    -- DART 공시 사건 라벨 (sql/36) — disclosure_collector 가 적재한 stock_event 를 선정 시점 집계.
    disc_count SMALLINT DEFAULT NULL,       -- 당일 공시 건수(정정 포함) — 관측·연구용
    disc_bad_type VARCHAR(24) DEFAULT NULL, -- 당일 최우선 악재 공시 타입(정정 제외) — veto_disclosure_bad 가 참조
    disc_good_type VARCHAR(24) DEFAULT NULL,-- 당일 대표 호재 공시 타입(정정 제외) — 관측·연구용
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
    --   selected=1 은 실제 매매 핸드오프된 종목, 0 은 비선정 후보. 판정은 선정 레이어
    --   (core.edge_selection.select_signals, EDGE_SELECTION_MODE)가 한다 — legacy 는 점수
    --   rank_no<=TRADED_TOP_N 이지만 hybrid/rules 모드에선 **점수 순위와 무관하게** live selector
    --   rule 매칭 종목이 우선 들어온다(rule_names 로 근거를 태깅). veto rule 은 제외만 한다.
    --   next_open_ret 은 리포트일 종가 → '다음 거래일 시가' 등락률(%). selected 무관 전 종목 균일
    --   백필(outcome_backfill 워커, 수정주가 차트로 분할 상쇄). 선정/비선정을 가르는 요인 측정용 라벨.
    selected TINYINT(1) DEFAULT 1 COMMENT '실매매 핸드오프 종목(1) / 비선정 후보(0)',
    rule_names VARCHAR(255) DEFAULT NULL COMMENT '선정 근거 edge_rule name 콤마 목록(hybrid/rules 모드) — NULL=점수순 선정 또는 비선정',
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
    dist_prior_high_pct FLOAT DEFAULT NULL COMMENT '250일 전고점(고가, 당일 제외) 대비 현재가 거리(%) — 음수=매물벽 아래, 양수=돌파',
    round_dist_pct FLOAT DEFAULT NULL COMMENT '최근접 라운드피겨(1·2·5×10^k원) 대비 현재가 거리(%) — 음수=직하단',
    ma5_reclaim TINYINT DEFAULT NULL COMMENT '5일선 재탈환(전일 5일선 아래 → 당일 5일선 위 양봉) — core.edge_features.ma5_reclaim',
    --   재무 스냅샷(2026-07-22): closing_bet 선정 시점 ka10001 응답 재사용(추가 콜 없음). 분기 저속 데이터,
    --   매일 같은 값 중복 저장 가능(연구용 무해). 점수 무영향. 부채비율은 ka10001 미제공이라 제외.
    fin_per FLOAT DEFAULT NULL COMMENT 'PER(배) — ka10001 per',
    fin_pbr FLOAT DEFAULT NULL COMMENT 'PBR(배) — ka10001 pbr',
    fin_ev FLOAT DEFAULT NULL COMMENT 'EV/EBITDA(배) — ka10001 ev',
    fin_roe FLOAT DEFAULT NULL COMMENT 'ROE(%) — ka10001 roe',
    fin_eps INT DEFAULT NULL COMMENT 'EPS 주당순이익(원) — ka10001 eps',
    fin_bps INT DEFAULT NULL COMMENT 'BPS 주당순자산(원) — ka10001 bps',
    fin_sales BIGINT DEFAULT NULL COMMENT '매출액(억원) — ka10001 sale_amt',
    fin_op_profit BIGINT DEFAULT NULL COMMENT '영업이익(억원) — ka10001 bus_pro',
    fin_net_income BIGINT DEFAULT NULL COMMENT '당기순이익(억원) — ka10001 cup_nga',
    op_earnings_yield FLOAT DEFAULT NULL COMMENT '영업이익÷시가총액(파생) — 0.1=영업이익이 시총 1/10, 적자면 음수 — core.edge_features.op_earnings_yield',
    --   호가 미시구조 스냅샷(2026-07-22): closing_bet 선정 시점 ka10004 파생. 연속장 중만 유효
    --   (장 종료 후 잔량 0→NULL, PRESERVE_ON_NULL 로 종가 직전 마지막 세션값 보존). 점수 무영향.
    ob_imbalance FLOAT DEFAULT NULL COMMENT '총매수잔량÷총매도잔량(>1 매수우위) — core.edge_features.order_book_features',
    ob_fpr_imbalance FLOAT DEFAULT NULL COMMENT '매수최우선잔량÷매도최우선잔량(1호가 압력)',
    ob_spread_pct FLOAT DEFAULT NULL COMMENT '(매도1호가−매수1호가)÷현재가 %(체결비용·유동성)',

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
    wti_ret         FLOAT DEFAULT NULL,   -- WTI 원유(CL=F) 등락률(%) — 지정학/유가 쇼크 프록시 연구용(2026-07-24 추가)
    ewy_ret         FLOAT DEFAULT NULL,   -- iShares MSCI Korea(EWY) 등락률(%) — 미국 세션 한국 프록시(2026-07-24 추가)
    koru_ret        FLOAT DEFAULT NULL,   -- Direxion Korea 3x Bull(KORU) 등락률(%) — 미국 세션 한국 레버리지 프록시(2026-07-24 추가)
    skhy_ret        FLOAT DEFAULT NULL,   -- SK하이닉스 ADR(SKHY) 등락률(%) — 미국 세션 반도체 프록시(2026-07-24 추가)
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
    min_sample    INT NOT NULL DEFAULT 40,           -- 참고값(매칭 종목-일) — 2026-07-28 승격 게이트에서 제외(단위가 거래일과 어긋나 좁은 룰을 막았음)
    registered_at DATE NOT NULL,                     -- ★ 사전 등록일 — 이 날짜 이후 표본만 승격 판정
    stats         JSON DEFAULT NULL,                 -- evaluator 캐시(n, mean_net, win_rate, std, ci_low, 초과 계열 mean_exc/ci_low_exc/t_days_exc, worst_low_ret, updated_through)
    decision      JSON DEFAULT NULL,                 -- 판정 기록(sql/39) {discovery, confirm, decided_at, verdict} — 재시험 금지용 영구 기록
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

-- ============================================================
-- 거시 이벤트 캘린더 (trading macro_gate 읽기 전용 조회)
-- FOMC·CPI·고용 등 예정 이벤트를 수동 시드(연 단위, sql/18 참고).
-- severity: 1 참고 / 2 주의(관찰 전용) / 3 중대(보유 창에 있으면 시드 감액)
-- 고갈 감시: workers/macro_event_check.py (월 08:20, 3주 내 바닥나면 경보)
-- ============================================================
CREATE TABLE IF NOT EXISTS macro_event (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    event_time DATETIME NOT NULL,                  -- 발표/결정 시각(KST)
    name       VARCHAR(100) NOT NULL,
    category   VARCHAR(20) NOT NULL,               -- rate | inflation | employment | other
    severity   TINYINT NOT NULL,
    source     VARCHAR(20) NOT NULL DEFAULT 'manual',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_macro_event (event_time, name),
    KEY idx_macro_event_time (event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 콘텐츠 스킵 기록 (LLM 분석까지 갔지만 저장하지 않기로 확정된 콘텐츠)
-- youtube_collector 가 15분마다 같은 영상을 재분석(Ollama 수 분/건)해
-- 타임아웃 나는 것을 막는 캐시. is_content_processed() 가 content_analysis 와
-- 함께 조회한다. 일시적 실패(LLM 오류·파싱 실패·자막 미생성)는 기록하지 않아
-- 다음 주기에 재시도된다. 보존 정책: cleanup_content 워커가 3개월 이전 삭제.
-- ============================================================
CREATE TABLE IF NOT EXISTS content_skip (
    external_id VARCHAR(255) NOT NULL PRIMARY KEY, -- 유튜브ID or 텔레그램Link
    platform    VARCHAR(20) NOT NULL DEFAULT 'youtube',
    source_name VARCHAR(100) DEFAULT NULL,          -- 채널명
    title       VARCHAR(255) DEFAULT NULL,
    reason      VARCHAR(30) NOT NULL,               -- irrelevant | no_companies | hallucination | no_ticker | analysis_timeout
                                                    -- | duplicate(채널 간 동일 본문) | backlog(LLM 대기 상한 초과 폐기) ← telegram_listener
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 뉴스 베토 판정 (trading monitor 읽기 전용 조회)
-- news_guard(평일 07:00~09:25)가 보유 종목의 밤사이 중대 악재를 OpenAI 로 판정해 기록하고,
-- trading monitor(08:01~09:30)가 severe=1 종목을 개장 즉시 전량 매도한다(sql/19 참고).
-- severe 는 GREATEST upsert 로 1→0 강등 금지(매도 진행 중 판정 뒤집힘 방지).
-- ============================================================
CREATE TABLE IF NOT EXISTS news_veto_verdict (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    verdict_date CHAR(8) NOT NULL,                 -- 매도 아침 거래일 YYYYMMDD (trading 조회 키)
    stk_cd VARCHAR(20) NOT NULL,
    stk_nm VARCHAR(100),
    severe TINYINT(1) NOT NULL DEFAULT 0,          -- 1=강제청산 대상(확신도 게이트 통과)
    confidence TINYINT,                            -- LLM 확신도 0~100
    category VARCHAR(20),                          -- 임상실패|계약파기|횡령배임|거래정지|규제제재|증자희석|사고재해|해당없음
    reason VARCHAR(500),
    headlines JSON,                                -- 판정에 쓴 헤드라인 스냅샷(감사·튜닝용)
    news_max_at DATETIME,                          -- 반영된 마지막 뉴스 created_at (신규 헤드라인 재판정 기준)
    model VARCHAR(40),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_news_veto (verdict_date, stk_cd),
    KEY idx_veto_date_severe (verdict_date, severe)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- ============================================================
-- 코스피200 야간선물 1분봉 (append-only 시계열) — 2026-08-03
--
-- [배경] trading/core/futures_gate.py 의 코스피 축은 '매수 시점의 전일대비 레벨'만 본다.
--   레벨은 매수가에 이미 반영된 후행 정보라, '매수 시점의 변화율(모멘텀)'로 축을 다시 잡는 게
--   맞는지 검증하려면 시점별 시계열이 필요하다. 그런데 kis_night_future 는 id=1 단일행
--   덮어쓰기라 이력이 전혀 없다(2026-08-03 확인 — 7/31 야간 붕괴도 마지막 틱 한 점만 남음).
--   여기서부터 1분봉을 쌓아 백테스트 표본을 만든다. **적재 전용 — 현재 어떤 매매 로직도 읽지 않는다.**
--
-- [쓰기] workers/kis_night_futures_ws.py — 야간세션(18:00~05:05) 분 경계마다 1행.
--        체결이 없는 분은 행을 만들지 않는다(빈 봉 생략 → 유동성 공백이 데이터에 그대로 남음).
-- [읽기] core/market_data.fetch_index_ohlc (K200NF 상세 차트), 추후 모멘텀 축 백테스트.
--
-- prev_close 를 함께 남기는 이유: change_percent 의 분모(주간 정산가)가 계약 교체·정정으로
--   바뀌어도 사후에 등락률을 재계산할 수 있게 하기 위함이다.
-- ============================================================
CREATE TABLE IF NOT EXISTS kis_night_future_bar (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol         VARCHAR(20) NOT NULL,            -- 근월물 코드 (예: A01609)
    bar_time       DATETIME NOT NULL,               -- 분 시작 시각(KST, 초=00)
    `open`         DECIMAL(10,2) NOT NULL,
    `high`         DECIMAL(10,2) NOT NULL,
    `low`          DECIMAL(10,2) NOT NULL,
    `close`        DECIMAL(10,2) NOT NULL,
    change_percent DECIMAL(6,2) DEFAULT NULL,       -- 봉 종가의 전일(주간 정산가) 대비 %
    prev_close     DECIMAL(10,2) DEFAULT NULL,      -- 그 시점 전일 정산가(등락률 사후 재계산용)
    tick_count     INT NOT NULL DEFAULT 0,          -- 그 분에 집계된 체결 수(유동성·신뢰도)
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_night_bar (symbol, bar_time),
    KEY idx_night_bar_time (bar_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
