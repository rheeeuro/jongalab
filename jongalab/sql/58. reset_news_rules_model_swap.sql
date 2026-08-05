-- 2026-08-05: 판정 모델 교체(gpt-5.4-nano → gpt-5.6-luna)에 따른 뉴스 라벨 rule 표본 리셋
--
-- [왜]
-- `news_durability`·`news_stage`·`news_milestone_horizon` 등 재료 라벨은 LLM 이 만든다.
-- 등급 **정의**(derive_durability v2)는 그대로지만 **판정 모델**이 바뀌면 라벨 분포가 바뀐다.
-- 같은 코퍼스(2026-08-05 유니버스 52종목) 실측:
--   · news_durability 미판정 15 → 5건 / 연속 9 → 18 / 중립 11 → 16 / 소진 17 → 13
--   · stage='불명' 15 → 5건, milestone_horizon='불명' 44 → 37건
--   · sentiment 평균 54.4 → 65.4 (범위 35~70 → 15~95, 진짜 악재는 더 낮게: 디앤디파마텍 28→15)
-- 모델이 다른 라벨을 한 표본으로 채점하면 nano 통계로 luna 룰을 승격시키는 셈이 된다
-- (sql/54 가 v1→v2 정의 변경에 쓴 것과 같은 논리 — `news_sector_label.model` 컬럼 코멘트
--  "모델 교체 시 표본 분리 근거"가 원래 이 경우를 위한 것이다).
--
-- [대상 4종] 재료 라벨 축을 predicate 에 쓰는 rule 만. 전부 candidate 라 live 매매 영향 없다.
--   f1_news_durable · veto_news_spent · f1_material_imminent · f1_material_unpriced
-- registered_at 이 2026-08-05(sql/54·55 에서 오늘 등록)이라 잃는 표본은 **1거래일**이다.
-- edge_rule_daily 채점 기록은 아직 0행(익일 백필 전)이므로 sql/57 같은 삭제는 필요 없다.
--
-- [대상 아님]
--   · veto_bad_news(live) — 근거 축이 news_sentiment 인데 표본이 7/7~ 이고 그 사이 이미
--     소스(Ollama→OpenAI)·코퍼스(텔레그램→네이버 포함)가 바뀐 혼합 표본이다. live 룰의
--     발견창을 여기서 리셋하면 지금까지의 채점 이력을 통째로 버리는 셈이라 손대지 않고,
--     문턱 30 의 재조정 필요 여부는 luna 라벨이 쌓인 뒤 게이트 재계산으로 판단한다.
--     (실측 방향은 오탐 감소 쪽: 평균이 +11 올라가고 진짜 악재만 더 내려갔다.)
--   · f1_fresh_news_unpriced / f1_news_surprise_burst — 카운트·시각 축이라 LLM 무관.
--
-- [실행 시점] `.env` 의 OPENAI_MODEL 을 gpt-5.6-luna 로 바꾼 **그날** 실행한다.
-- registered_at 을 CURDATE() 가 아니라 **다음 날**로 잡는 이유: 재료 라벨은 closing_bet
-- 선정(15:30)에서 붙으므로 교체일 당일 행은 이미 구 모델(nano)이 만든 라벨이다. 교체를 장 시작
-- 전에 했다면 CURDATE() 로 바꿔도 된다(그 경우 하루 이득). 교체가 미뤄지면 실행일 기준으로
-- 알아서 잡히므로 파일은 그대로 쓴다.
--
-- [실행 기록] 2026-08-05 실행 완료 — 4행 갱신(registered_at=2026-08-06, stats/decision NULL).
-- 되돌리려면 같은 4종의 registered_at 을 2026-08-05 로 UPDATE 하면 된다(채점 기록은 0행이었다).

UPDATE edge_rule
SET registered_at = CURDATE() + INTERVAL 1 DAY,
    stats = NULL,
    decision = NULL
WHERE name IN ('f1_news_durable', 'veto_news_spent',
               'f1_material_imminent', 'f1_material_unpriced');
