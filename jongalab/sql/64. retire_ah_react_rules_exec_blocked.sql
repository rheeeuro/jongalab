-- 2026-08-13 — 시간외 반응 rule 2종을 '실행 불가'로 종료 (사용자 결정)
--
-- 대상: f6_ah_react_up(id 27, selector) · veto_ah_react_down(id 28, veto)
--
-- 왜 종료인가 — **통계가 나빠서가 아니라 매수 경로가 구조적으로 없어서**다.
-- `ah_react`/`ah_volume`(ka10087)은 시간외단일가 세션(16~18시) 중에만 값이 살아 있어 17:50 에
-- 수집한다. 그런데 그 값이 채워지는 행은 **전부 `nxt_listed=0`** 이다(NXT 상장 480행 100% NULL,
-- 배타적). 즉 신호가 있는 종목은 NXT 매수(19:50) 대상이 아니고, 그 종목의 유일한 매수 창인
-- KRX 종가(15:20)는 수집(17:50)보다 **앞선다**. 어느 레이어에서도 평가 시점이 존재하지 않는다.
--
-- 같은 날 `veto_short_surge`·`f2_us_semis_laggard` 는 반대로 **게이트 오분류**였음이 확인돼
-- 살렸다(14:30 선반영 회차 추가 + 화이트리스트 정정). 이 2종만 진짜 구조적 불가로 남는다.
-- 경위·실측은 docs/history/edge-ledger.md 2026-08-13 항목.
--
-- 채점은 종료 후에도 계속된다(rule_evaluator 가 retired 까지 채점) — 표본은 계속 쌓이므로
-- 집행 설계가 바뀌면(예: KRX 매수 창을 시간외단일가로 이동) 그때 새 rule 로 재등록해 판정한다.
-- `registered_at` 을 살린 재개는 하지 않는다(사전 등록 원칙).

UPDATE edge_rule
   SET status      = 'retired',
       retired_at  = CURRENT_TIMESTAMP,
       -- 기존 decision(발견 판정 기록)은 보존하고 종결 사유만 덧붙인다.
       -- JSON_MERGE_PATCH 는 decision 이 NULL 이면 NULL 을 반환하므로 COALESCE 로 감싼다
       -- (f6_ah_react_up 은 n_days=6 이라 아직 판정 기록이 없다).
       decision    = JSON_MERGE_PATCH(
                         COALESCE(decision, JSON_OBJECT()),
                         JSON_OBJECT(
                             'decided_at',   '2026-08-13',
                             'verdict',      'exec_blocked',
                             'retire_reason',
                             '시간외단일가 값(17:50 수집)은 이 종목들의 유일한 매수 창인 KRX 종가(15:20)보다 늦게 나오고, 값이 채워지는 종목은 NXT 매수 대상이 아니라 19:50 경로도 쓸 수 없습니다. 성적과 무관하게 실제 매매에 반영할 방법이 없어 종료했습니다.'
                         )
                     )
 WHERE name IN ('f6_ah_react_up', 'veto_ah_react_down');
