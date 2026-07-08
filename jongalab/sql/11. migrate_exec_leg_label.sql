-- 실집행 레그 통합 라벨 추가 (2026-07-08)
-- 목적: rule_evaluator 의 기본 채점을 실제 청산 venue 창과 맞춘다.
--   NXT: 전일 19:50 NXT → 익일 08:03 NXT
--   KRX: 전일 15:20 KRX → 익일 09:03 KRX
--
-- 주의: exit_label 전환 후 기존 edge_rule_daily 는 과거 라벨 기준이므로 삭제하고
--       workers/rule_evaluator.py 를 다시 실행해 exec_leg_ret 기준으로 재채점한다.

ALTER TABLE daily_stock_report
    ADD COLUMN exec_leg_ret FLOAT DEFAULT NULL COMMENT '실집행 청산창 등락률(%): NXT 19:50→08:03 / KRX 15:20→09:03' AFTER gap_checked_at,
    ADD COLUMN exec_leg_venue VARCHAR(3) DEFAULT NULL COMMENT 'exec_leg_ret 산출 venue: NXT 또는 KRX' AFTER exec_leg_ret;

ALTER TABLE edge_rule
    MODIFY exit_label VARCHAR(30) NOT NULL DEFAULT 'exec_leg_ret';

UPDATE edge_rule
   SET exit_label = 'exec_leg_ret',
       stats = NULL
 WHERE status <> 'retired';

DELETE d
  FROM edge_rule_daily d
  JOIN edge_rule r ON r.id = d.rule_id
 WHERE r.status <> 'retired';
