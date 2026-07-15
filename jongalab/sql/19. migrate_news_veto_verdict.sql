-- 뉴스 베토 판정 — 보유 종목의 밤사이 중대 악재(시초가 갭하락이 거의 확실한 뉴스) 기록.
-- jongalab workers/news_guard.py(평일 07:00~09:25, 5분 폴링)가 보유 종목(trading.position)의
-- news_mention 헤드라인을 OpenAI 로 판정해 적재하고, trading workers/monitor.py(08:01~09:30)가
-- 읽기 전용 조회(severe=1)해 해당 종목을 개장 즉시 가장 이른 거래소에서 전량 매도한다.
-- 배경: HLB 하한가 사건(2026-07-10)류 — FDA 승인 실패·대형 계약 파기 등은 정상 청산 흐름
-- (NXT 08:03 반매도 → 09:28 전량청산)을 기다리지 않고 즉시 탈출해야 손실이 준다.
-- severe 는 GREATEST upsert 로 1→0 강등을 금지한다(매도 진행 중 판정 뒤집힘 방지).

CREATE TABLE IF NOT EXISTS news_veto_verdict (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    verdict_date CHAR(8) NOT NULL COMMENT '매도 아침 거래일 YYYYMMDD — trading 조회 키',
    stk_cd VARCHAR(20) NOT NULL,
    stk_nm VARCHAR(100),
    severe TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=강제청산 대상(LLM severe + 확신도 게이트 통과)',
    confidence TINYINT COMMENT 'LLM 확신도 0~100',
    category VARCHAR(20) COMMENT '임상실패|계약파기|횡령배임|거래정지|규제제재|증자희석|사고재해|해당없음',
    reason VARCHAR(500),
    headlines JSON COMMENT '판정에 쓴 헤드라인 스냅샷(감사·튜닝용)',
    news_max_at DATETIME COMMENT '판정에 반영된 마지막 뉴스 created_at — 신규 헤드라인 재판정 기준',
    model VARCHAR(40),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_news_veto (verdict_date, stk_cd),
    KEY idx_veto_date_severe (verdict_date, severe)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
