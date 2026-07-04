-- 엣지 피처 스냅샷 확장 (Phase 1, 2026-07-04)
-- 목적: 가설 F1~F4 가 "볼 수 있는 것"을 넓힌다. 기록하지 않은 피처는 영원히 검증할 수 없다.
--       이 마이그레이션은 매매 행위에 영향 0 — 순수 관측·기록 레이어.
--
-- (A) daily_stock_report 종목 단위 피처 7컬럼
--   NXT 스냅샷(F3 NXT 괴리형의 눈, gap_check --base-nxt 19:50 수집):
--     krx_close_price — 15:30 확정 종가(19:50 수집. current_price 는 13~15시 장중가라 별도)
--     nxt_price_1950  — 19:50 NXT 현재가(미상장/무거래 NULL)
--     nxt_gap_pct     — KRX 확정 종가 → 19:50 NXT 괴리율(%)
--     nxt_after_value — NXT 세션 누적 거래대금 근사(원). ka10001 에 거래대금 필드가 없어
--                        거래량(trde_qty)×현재가 근사(순수 애프터마켓 아님, NXT 세션 전체)
--     nxt_listed      — 19:50 NXT 조회 성공 여부(NXT 상장 판별)
--   섹터 상대치(F4 후발 확산형의 눈, closing_bet 저장 시점 파생 — API 콜 없음):
--     sector_rel_ret    — 당일 등락률 − 유니버스 내 동일 sector 평균 등락률(%p)
--     sector_leader_chg — 유니버스 내 동일 sector 최고 등락률(%) — 후발주 판정 분모
--
-- (B) market_snapshot 테이블 신설 (일 단위 시장 피처, F2 해외 동조·레짐 연구용)

ALTER TABLE daily_stock_report
    ADD COLUMN krx_close_price INT DEFAULT NULL COMMENT '15:30 확정 종가(19:50 수집)' AFTER next_open_ret,
    ADD COLUMN nxt_price_1950 INT DEFAULT NULL COMMENT '19:50 NXT 현재가(미상장/무거래 NULL)' AFTER krx_close_price,
    ADD COLUMN nxt_gap_pct FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가 → 19:50 NXT 괴리율(%)' AFTER nxt_price_1950,
    ADD COLUMN nxt_after_value BIGINT DEFAULT NULL COMMENT 'NXT 세션 누적 거래대금 근사(거래량×현재가)' AFTER nxt_gap_pct,
    ADD COLUMN nxt_listed TINYINT(1) DEFAULT NULL COMMENT '19:50 NXT 조회 성공 여부(NXT 상장 판별)' AFTER nxt_after_value,
    ADD COLUMN sector_rel_ret FLOAT DEFAULT NULL COMMENT '당일 등락률 − 동일 sector 평균 등락률(%p)' AFTER nxt_listed,
    ADD COLUMN sector_leader_chg FLOAT DEFAULT NULL COMMENT '동일 sector 최고 등락률(%) — 후발주 판정 분모' AFTER sector_rel_ret;

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
