-- 2026-08-19 — edge_rule 에 `paused` 상태 추가 (사용자 결정)
--
-- 왜 필요한가 — 강등이 **편도**라 아무도 누르지 않았다. 라우터가 `candidate` 상태만 승격을
-- 받으므로(routers/edge_rule.promote_edge_rule) 한 번 retired 로 내리면 되돌릴 수 없다.
-- 그 결과 강등 게이트는 매 평일 후보를 띄우는데 실제 강등은 0건이었다.
-- → 상태 축을 둘로 나눈다:
--     원장(느림·사람): candidate → live / retired,  retired → candidate(표본 리셋)
--     운용(빠름·자동): live ↔ paused
--   `paused` = 선정에서 표를 주지 않는다. 채점·통계는 계속한다. 되돌릴 수 있다.
--
-- 실매매 경로는 코드 변경이 필요 없다 — jongalab/workers/closing_bet.py 와
-- trading/core/repository/edge_rule.py 가 둘 다 `status='live'` 만 조회하므로
-- paused 는 자동으로 선정·집행에서 빠진다.
--
-- 근거·실측(전이 빈도, 적응형 창, 0표 슬롯 영향)은 docs/history/edge-ledger.md 2026-08-19 항목.

ALTER TABLE edge_rule
    MODIFY COLUMN status VARCHAR(10) NOT NULL DEFAULT 'candidate'
        COMMENT 'candidate / live / paused(운용 일시중지 — 표 미부여, 채점 계속) / retired',
    -- 마지막 live<->paused 전이 시각. 자동 전이라 자주 갱신되며 '얼마나 오래 쉬는 중인가'를
    -- 화면에서 읽기 위한 값이다(전이 이력 자체는 남기지 않는다 — 원장이 아니라 운용 상태).
    ADD COLUMN paused_at TIMESTAMP NULL DEFAULT NULL AFTER retired_at;
