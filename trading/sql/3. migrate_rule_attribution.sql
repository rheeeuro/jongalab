-- rule_id 귀속 관통 (Phase 4, 2026-07-04)
-- trade_signal 에 선정 근거 edge_rule 이름 목록을 nullable 컬럼으로 추가한다.
-- 목적: 모든 원(₩)이 "어느 가설의 돈인지"를 달고 다니게 한다(실현손익 → rule 귀속).
--
-- ⚠️ trading 도메인 로직은 무변경: risk_engine·execution_engine·seed_allocator 는 이 컬럼을
--    읽지 않는다(하위호환). 실현손익→rule 귀속은 trade_signal ⨝ audit_log/fill 조인으로
--    jongalab 쪽에서 계산한다. NULL = legacy 점수 선정(rule 미태깅).

USE trading;

ALTER TABLE trade_signal
    ADD COLUMN rule_names VARCHAR(200) DEFAULT NULL
        COMMENT '선정 근거 edge_rule name 목록(콤마) — NULL=legacy 점수 선정' AFTER score;
