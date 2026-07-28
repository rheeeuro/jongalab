-- 사건(event) 계층 — DART 전자공시 수집 (2026-07-28, 뉴스 파이프라인 재설계 1단계)
--
-- 배경: 기존 뉴스 파이프라인은 news_mention(언급 원자료) 한 계층뿐이라
--   · 세는 축이 '언급 수'여서 시총 프록시에 불과했고(대형주는 매일 수십 건),
--   · 사전 regex 매칭이라 당사자/곁다리 구분이 안 됐고,
--   · 14일 보존이라 과거 검증이 원천 불가했다.
-- → 원자료 위에 **사건 계층(stock_event)**을 둔다. 1행 = 종목×사건 1건, 영구 보존.
--
-- 첫 소스로 DART 공시를 넣는 이유(뉴스보다 먼저):
--   · stock_code 로 당사자가 확정된다 → 매칭 오탐 0.
--   · report_nm(보고서명)이 그 자체로 이벤트 타입이다 → LLM 없이 룰로 분류된다.
--   · 종가베팅의 빈 구간을 메운다: 유상증자·CB·공급계약 등 익일 시초가를 가장 세게
--     움직이는 공시가 15:30~18:00 에 몰리는데, 이 창은 KRX 매수(15:20)와
--     NXT 매수(19:50) 사이라 지금까지 아무도 보지 않았다.
--
-- [접수 시각 주의] DART list.json 은 rcept_dt(YYYYMMDD)만 주고 접수 '시각'은 안 준다.
--   그래서 first_seen_at 에 **수집기가 처음 관측한 시각**을 기록한다(폴링 주기 ±30분 오차).
--   "이 공시가 19:00 선정 시점에 이미 있었는가"를 판정하는 데는 이 값으로 충분하고,
--   장중/장마감후 창 구분(연구용)도 이 해상도면 된다.
--
-- source 는 'dart' 로 시작하지만 컬럼은 소스 중립이다 — 뉴스(source='news')를 같은
-- 사건 계층으로 접어 넣는 것이 후속 단계다(그때 news_mention → stock_event 정규화 추가).

CREATE TABLE IF NOT EXISTS stock_event (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker        VARCHAR(20)  NOT NULL COMMENT '종목코드(6자리) — daily_stock_report.stock_code 와 조인',
    event_date    DATE         NOT NULL COMMENT '접수일(DART rcept_dt)',
    source        VARCHAR(10)  NOT NULL COMMENT '출처: dart (향후 news)',
    source_key    VARCHAR(40)  NOT NULL COMMENT '출처 고유키 — DART 접수번호(rcept_no). 멱등 수집의 근거',
    event_type    VARCHAR(24)  NOT NULL COMMENT '분류 결과 — core.disclosure_events.classify (유상증자/공급계약/무상증자/...)',
    direction     TINYINT      NOT NULL DEFAULT 0 COMMENT '+1 호재 / 0 중립·미상 / -1 악재',
    is_veto_type  TINYINT      NOT NULL DEFAULT 0 COMMENT '1 = 선정 제외 대상 악재 타입(희석·존속위험·계약해지·불성실공시)',
    is_subject    TINYINT      NOT NULL DEFAULT 1 COMMENT '1 = 접수 종목이 사건 당사자. 0 = 종속회사·출자법인 건(direction·veto 를 0 으로 눕힘)',
    is_correction TINYINT      NOT NULL DEFAULT 0 COMMENT '1 = [기재정정]·[첨부정정] 정정공시 — veto 집계에서 제외(원 공시가 이미 그날 처리됨)',
    first_seen_at DATETIME     NOT NULL COMMENT '수집기가 처음 관측한 시각(접수시각 근사, 폴링주기 오차) — 선정 시점 가용성 판정용',
    title         VARCHAR(255) NOT NULL COMMENT 'DART report_nm 원문',
    corp_name     VARCHAR(80)  DEFAULT NULL,
    raw_url       VARCHAR(255) DEFAULT NULL COMMENT 'DART 원문 뷰어 링크',
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_source_key (source, source_key),
    INDEX idx_ticker_date (ticker, event_date),
    INDEX idx_date_type (event_date, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 이미 만든 테이블에 뒤늦게 추가된 컬럼(2026-07-28 첫 실수집 오탐 감사 반영) — 재실행 안전.
ALTER TABLE stock_event
    ADD COLUMN IF NOT EXISTS is_subject TINYINT NOT NULL DEFAULT 1
        COMMENT '1 = 접수 종목이 사건 당사자. 0 = 종속회사·출자법인 건'
        AFTER is_veto_type;

-- ── daily_stock_report 공시 라벨 (closing_bet 선정 시점에 stock_event 에서 집계) ──
-- disc_bad_type 은 veto rule(sql/37)이 predicate 로 참조하는 유일한 컬럼이다.
-- 결측(공시 없음·수집 실패)은 NULL → predicate 매칭 실패 → veto 미개입(fail-safe).
ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS disc_count SMALLINT DEFAULT NULL
        COMMENT '당일 공시 건수(정정 포함) — 관측·연구용, 점수 무영향'
        AFTER news_headlines,
    ADD COLUMN IF NOT EXISTS disc_bad_type VARCHAR(24) DEFAULT NULL
        COMMENT '당일 악재 공시 중 최우선 타입(정정 제외) — veto rule 이 in 으로 참조. 없으면 NULL'
        AFTER disc_count,
    ADD COLUMN IF NOT EXISTS disc_good_type VARCHAR(24) DEFAULT NULL
        COMMENT '당일 호재 공시 중 대표 타입(정정 제외) — 관측·연구용, 점수 무영향'
        AFTER disc_bad_type;
