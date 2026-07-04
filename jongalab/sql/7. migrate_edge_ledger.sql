-- Edge Ledger — 가설 원장 (Phase 3, 2026-07-04)
-- 시스템의 1급 시민을 "오늘의 종목"에서 "가설(rule)"로 바꾸는 심장부. 모든 가설은 DB 행으로
-- 존재하고, rule_evaluator(09:40)가 매일 자동 채점하며, 표본·성적으로만 승격된다(수동 게이트).
-- 순수 관측·기록·평가 레이어 — 매매 집행 연결은 Phase 4.

-- 가설 원장. 1행 = 반증가능한 가설 1개.
CREATE TABLE IF NOT EXISTS edge_rule (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL UNIQUE,       -- 예: f3_nxt_gap_quality
    family        VARCHAR(20) NOT NULL,              -- f1_news / f2_global / f3_nxt / f4_laggard / control / veto
    description   VARCHAR(500) NOT NULL,             -- 인과 근거 필수: "누가 왜 내일 아침 사는가"
    predicate     JSON NOT NULL,                     -- 조건 목록(AND 결합, core/edge_predicate.py DSL)
    exit_label    VARCHAR(30) NOT NULL DEFAULT 'next_open_ret',  -- 채점에 쓸 결과 라벨 컬럼
    status        VARCHAR(10) NOT NULL DEFAULT 'candidate',      -- candidate / live / retired
    min_sample    INT NOT NULL DEFAULT 40,           -- 승격 심사 최소 표본(매칭 종목-일)
    registered_at DATE NOT NULL,                     -- ★ 사전 등록일 — 이 날짜 이후 표본만 승격 판정에 사용
    stats         JSON DEFAULT NULL,                 -- evaluator 갱신 캐시(n, mean_net, win_rate, std, ci_low, worst_low_ret, updated_through)
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    promoted_at   TIMESTAMP NULL DEFAULT NULL,
    retired_at    TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 일별 평가 결과 (스코어보드 시계열 + 감사 추적).
--   matched: [{code, name, ret, low}] — ret=exit_label 값, low=next_low_ret(꼬리 심사).
--   비용 미차감 원본 ret 을 남겨 언제든 수동 재검산 가능(EDGE_COST_PCT 보정 시 소급 재계산).
CREATE TABLE IF NOT EXISTS edge_rule_daily (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id      INT NOT NULL,
    report_date  DATE NOT NULL,
    n_matched    INT NOT NULL DEFAULT 0,
    mean_net_ret FLOAT DEFAULT NULL,                 -- 매칭 종목 평균 (exit_label − EDGE_COST_PCT)
    matched      JSON DEFAULT NULL,                  -- [{code, name, ret, low}] 감사·복기용
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_rule_date (rule_id, report_date),
    INDEX idx_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
