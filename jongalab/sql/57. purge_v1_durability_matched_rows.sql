-- 2026-08-05: 지속성 rule 2종의 **v1 구간 매칭 기록 삭제** (sql/54 리셋의 마무리)
--
-- [왜]
-- sql/54 에서 `f1_news_durable`·`veto_news_spent` 의 `stats`·`decision` 을 비우고
-- `registered_at` 을 8/5 로 리셋했지만 `edge_rule_daily`(날짜별 매칭 종목 기록)는 남겼다.
-- 그 결과 화면이 **"누적 성적은 비어 있는데 매칭 기록에는 7/29~8/4 가 보이는"** 상태가 됐다.
-- 게이트는 `registered_at` 이후만 집계하므로 숫자는 정확했지만, 읽는 사람에게는 같은 룰의
-- 성적이 두 군데서 다르게 보인다 — 사용자 판단으로 그 10행을 지운다(2026-08-05).
--
-- [무엇을 잃나 — 알고 지운다]
-- v1 라벨 정의로 채점된 5거래일치 기록이다(f1_news_durable 5행 · veto_news_spent 5행):
--   f1_news_durable  7/29 -2.892 / 7/30 +7.032 / 7/31 +0.174 / 8/3 +3.834 / 8/4 +1.862
--   veto_news_spent  7/29 -3.413 / 7/30 +5.742 / 7/31 +0.184 / 8/3 +3.469 / 8/4 +3.469
-- 애초에 승격 판정에 쓸 수 없는 표본이었다(라벨 정의가 다르고, `SELECTION_TIME_COLS` 누락으로
-- 그 기간 두 룰은 실행 불가 판정 상태였다). 위 수치를 주석에 남겨 두는 것으로 갈음한다.
-- 원자료(`daily_stock_report` 의 news_* 라벨과 결과 라벨)는 그대로이므로 필요하면 재계산도 된다.
--
-- [범위] `report_date < registered_at` 인 행만 — 8/5 이후 채점분은 v2 표본이라 건드리지 않는다.
-- 다른 rule 은 대상이 아니다(리셋한 두 종만).

DELETE d FROM edge_rule_daily d
  JOIN edge_rule r ON r.id = d.rule_id
 WHERE r.name IN ('f1_news_durable', 'veto_news_spent')
   AND d.report_date < r.registered_at;
