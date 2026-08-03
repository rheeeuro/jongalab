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
