-- Edge Ledger 판정 일정 (2026-07-28) — '매일 재평가' 무력화 문제의 해법
--
-- 문제: rule_evaluator 가 매 평일 승격 게이트를 다시 검사해, 룰 하나가 무기한 재시험을 친다
--       (optional stopping). 시뮬레이션(일간 초과 sd 2.43%p, 진짜 엣지 0):
--         · 오탐율 명목 5% → 실제 22%
--         · candidate 24종이 전부 무엣지여도 60거래일 내 최소 1건 발생 확률 99.8%(기대 5.2건)
--       실제로 2026-07-28 승격 알림 4건 중 3건이 수동 재계산에서 뒤집혔다.
--
-- 기각한 대안: '최근 N일 롤링'. 창 크기가 고정이라 W거래일마다 사실상 새 시험을 치므로
--       더 나쁘다(가짜 룰 200개 모의: 롤링20 은 90%가 승격 후보로 뜸 vs 누적 32%).
--       누적은 새 표본 가중이 1/n 이라 t 가 점점 안 움직여 새 기회가 덜 생긴다.
--
-- 해법: 시험 횟수를 묶는다.
--   발견(누적 거래일 1~10) → 통계 게이트 → 통과 시 확인창(11~20)의 **발견에 안 쓴 새 표본**으로
--   재확인 → 확인 시점에 단 1회 판정하고 종결. 오탐 22% → 2.4%.
--   판정 기준·단계 정의는 core/edge_policy.py (DISCOVERY_DAYS·CONFIRM_DAYS·check_confirmation).
--
-- 자동 전이는 하지 않는다 — 판정 결과만 기록하고 알림을 멈춘다. candidate→live 는 여전히
-- 관리자 API 수동 승인이다(탈락 rule 의 retire 도 관리자 판단).

ALTER TABLE edge_rule
    ADD COLUMN decision JSON DEFAULT NULL
        COMMENT '판정 기록 {discovery:{at,n_days,pass,reasons,...}, confirm:{...}, decided_at, verdict} — 재시험 금지용 영구 기록(stats 와 달리 재계산 대상 아님)'
        AFTER stats;

-- 기존 rule 은 decision=NULL → 발견 단계로 시작한다. 이미 거래일 10일을 넘긴 rule 은
-- 다음 rule_evaluator 실행에서 즉시 발견 판정을 받는다(과거 표본이 이미 있으므로 정당).
