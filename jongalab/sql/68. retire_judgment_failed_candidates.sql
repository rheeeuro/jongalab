-- 2026-08-21 — 판정 탈락(discovery_failed / confirm_failed) candidate 를 retired 로 내림 (사용자 결정)
--
-- 왜 필요한가 — **판정이 편도였다.** 발견창에서 떨어지면 `decision.verdict` 만 찍고 상태는
-- candidate 로 남겼는데, `decision_stage` 가 영구히 `decided` 라 `decision_due` 가 None 이다.
-- → 이후 표본이 아무리 쌓여도 **자동 재판정 경로가 없다.**
-- 그런데 누적 게이트(`check_promotion`)는 새 표본까지 포함해 매일 재계산되므로, 탈락한 룰이
-- 화면 '검증 통과'와 수동 승격 버튼에는 계속 올라온다 — 즉 **다시 판정할 앞문은 없고 뒷문만
-- 열린** 상태였다. 2026-08-19 에 강등이 편도라 아무도 버튼을 못 눌렀던 것과 같은 구조다.
--
-- 실례 `f5_foreign_broker_top`: 발견창 ci_low -0.411 로 08-10 탈락 → 이후 4거래일이 붙어
-- 누적 ci_low +0.356 으로 게이트 통과 상태가 됐다. 그러나 그 개선의 68%가 08-13 **하루**
-- (SK하이닉스 +7.52·SK스퀘어 +9.41·한미반도체 +5.12·효성중공업 +2.69)에서 나왔고, 그 하루를
-- 빼면 ci_low -0.301 로 그대로 탈락한다(t_days 0.79 → 0.15). 하루로 뒤집히는 자로 실탄에
-- 오르는 경로만 열려 있었다는 뜻이다.
--
-- → retired 로 내리면 `unretire`(= `registered_at` 을 오늘로 밀어 **표본 리셋**)가 유일한
--   재도전 경로가 된다. 같은 표본 재시험(optional stopping)을 막으면서 길은 열린다.
--   채점은 retired 여도 계속되므로(2026-07-31 결정) 표본은 끊기지 않는다.
--
-- 앞으로는 `workers/rule_evaluator._auto_retire` 가 판정일에 자동으로 내린다. 이 마이그레이션은
-- 그 이전에 쌓인 13종을 같은 상태로 맞추는 1회성 소급 적용이다.
-- 근거·경위: docs/history/edge-ledger.md 2026-08-21 항목.

UPDATE edge_rule
   SET status     = 'retired',
       retired_at = CURRENT_TIMESTAMP,
       -- 기존 판정 기록은 보존하고 종결 사유만 덧붙인다(화면이 그대로 보여주는 문장).
       -- JSON_MERGE_PATCH 는 인자가 NULL 이면 NULL 을 반환하므로 COALESCE 로 감싼다.
       decision   = JSON_MERGE_PATCH(
                        COALESCE(decision, JSON_OBJECT()),
                        JSON_OBJECT(
                            'retire_reason',
                            '판정에서 실전 투입 기준에 못 미쳐 종결했습니다. 다시 도전하려면 ''재검증''으로 되돌리세요 — 오늘부터 쌓이는 새 표본으로 처음부터 판정합니다(같은 표본으로 다시 시험하지는 않습니다).'
                        )
                    )
 WHERE status = 'candidate'
   AND JSON_VALUE(decision, '$.verdict') IN ('discovery_failed', 'confirm_failed');
