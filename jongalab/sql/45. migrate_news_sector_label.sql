-- ============================================================
-- 미매칭 뉴스 → 섹터·거시 라벨 (2026-08-03) — **관측 전용, 점수·시드 무영향**
--
-- [왜] 뉴스 파이프라인은 `news_matcher` 가 사명을 잡아야만 `news_mention` 에 들어가고,
--   그 뒤 재료판정·veto·점수가 전부 ticker 키로 돈다. 섹터는 `sector_resolver` 가
--   **이미 매칭된 티커**에서 역으로 끌어오는 구조라, 사명 없는 뉴스(정책·산업·지정학)는
--   섹터로도 못 간다. 실측 텔레그램 수집률 34%(2026-07-31, 적재 630 / no_match 1236) —
--   나머지 66%는 `content_skip(platform='news', reason='no_match')` 에 헤드라인만 쌓인다.
--   이 테이블은 그 코퍼스에 **섹터 + 방향** 라벨을 붙여 검정 표본을 만든다.
--
-- [왜 지금 live 가 아닌가] 2026-08-03 사전검정(daily_stock_report 4/9~7/31, 1159행):
--   · 섹터 공통요인은 **실재**한다 — 일별 평균을 뺀 잔차를 섹터 라벨이 R²=0.486 설명
--     (동일날짜 안에서 라벨을 섞은 귀무는 0.178, p<0.002). 같은 섹터는 같이 움직인다.
--   · 그러나 그건 **사후 구조**지 예측력이 아니다. 사전 예측 쪽은 약하거나 없다:
--     `sector_rel_ret`(당일 섹터 상대수익) → 익일 시가 corr +0.093(t=+2.42)로 유의하나
--     상·하위⅓ 차이는 t=+1.58 미달, **섹터 뉴스 건수 → 익일 시가는 corr +0.009(t=+0.16)
--     무신호**(매칭 뉴스를 섹터로 접어 측정, 7/20~7/29 343행).
--   → 건수 축은 이미 죽었다. 남은 미검증 지점은 **방향(호재/악재)과 미매칭 코퍼스**뿐이고,
--     그건 라벨이 없으면 영원히 못 잰다. 그래서 **적재만** 하고 소비는 하지 않는다.
--     (naver 소스를 `NEWS_ACTIVE_SOURCES` 로 막고 관측만 한 sql/44 선례와 같은 규율.)
--
-- [왜 거시 라벨도 남기나] 지정학·거시 축은 2026-08-03 백테스트에서 이미 기각됐다 —
--   밤사이 갭 전달 경로는 NQ 선물(t=+3.69)이고 WTI 는 보유한 그 밤의 실변동조차 t=+0.42
--   (trading/core/macro_gate.py docstring 참조). 다만 그 기각은 **가격 프록시**(VIX/WTI/FX)
--   기준이고 뉴스 텍스트 채널로는 재본 적이 없다. 라벨링하는 김에 공짜로 남는 부산물이라
--   scope='거시' 로 적재만 한다. **이걸 근거로 시드를 깎는 코드를 붙이지 말 것** —
--   붙이려면 futures_gate 와 min 결합이지 곱이 아니고, 그 전에 승격 검정이 먼저다.
--
-- [왜 헤드라인 단위인가] (날짜×섹터) 집계로 저장하면 나중에 창(장중/마감후/밤사이)을 못 자른다.
--   종가베팅은 15:30 매수 → 익일 시가 청산이라 "언제 나온 뉴스인가"가 축의 핵심 변수다.
--   행 수는 하루 수백 건이라 무시 가능하고, 집계는 조회 시점에 접으면 된다.
--
-- [멱등] PK = content_skip.external_id(기사 링크) → 재실행·백필 중복 없음.
-- [보존] content_skip 과 같은 3개월(cleanup_content). 원본이 지워지면 라벨만 남아도 무해하다.
-- ============================================================

CREATE TABLE IF NOT EXISTS news_sector_label (
    external_id VARCHAR(255) NOT NULL PRIMARY KEY
        COMMENT 'content_skip.external_id (기사 링크) — 재실행 멱등 키',
    news_at     DATETIME NOT NULL
        COMMENT 'content_skip.created_at (수집 시각). 창 분석 기준 — 집계는 조회 시점에 접는다',
    scope       VARCHAR(10) NOT NULL
        COMMENT '섹터 | 거시 | 무관 — 무관도 저장한다(프리필터·LLM 오탐률 감사용 분모)',
    sector      VARCHAR(50) DEFAULT NULL
        COMMENT 'daily_stock_report.sector 와 같은 어휘(키움 upName). scope<>섹터면 NULL',
    sentiment   TINYINT UNSIGNED DEFAULT NULL
        COMMENT '0~100 방향 (호재>50, 악재<50, 중립=50). news_material_judge 규약과 동일',
    headline    VARCHAR(255) DEFAULT NULL COMMENT '판정 근거 원문(발행처·URL 제거 후)',
    reason      VARCHAR(255) DEFAULT NULL COMMENT '판정 근거 한 문장(육안 감사용)',
    model       VARCHAR(50)  DEFAULT NULL COMMENT '판정 모델 — 모델 교체 시 표본 분리 근거',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- 검정 쿼리는 항상 "기간 × 섹터"로 접는다
    INDEX idx_at_sector (news_at, sector),
    INDEX idx_scope (scope)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
