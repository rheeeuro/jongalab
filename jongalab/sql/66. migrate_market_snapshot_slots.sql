-- 2026-08-21 market_snapshot 을 **시각 슬롯 다행** 구조로 (PK: snapshot_date → (snapshot_date, slot))
--
-- 배경: 저장이 하루 1행 전체 덮어쓰기라 최종값은 항상 19:50 회차 것이었다. 그런데 집행은
--   KRX 15:20 / NXT 19:50 이고 채점(rule_evaluator)은 그 최종값을 본다 — 시각에 따라 값이
--   달라지는 축(선물·VIX·환율·코스피/코스닥)은 **채점 표본 ≠ 집행 값**이 되어 통째로 봉인돼
--   있었다(edge_policy.SELECTION_TIME_MARKET_COLS = sox_ret·spx_ret 둘뿐).
--   축이 없어서 못 쓴 게 아니라 저장 구조가 축을 막고 있었다.
--
-- 슬롯 = **그 스냅샷을 굽는 시각**. 선정과 채점이 같은 슬롯을 읽어 두 값이 '같은 행'이 되므로
--   정의상 어긋날 수 없다(nxt_gap_pct 가 성립하는 것과 같은 규율).
--     '1430' : 14:30 회차(gap_check --market-snap). **rule 이 쓰는 유일한 시황 축.**
--              closing_bet 선정(15:10·19:40 회차)과 rule_evaluator 채점이 이 행만 읽는다.
--     '1950' : 19:50 회차(gap_check --base-nxt 말미, 실제로는 종목 루프 뒤라 ≈19:52).
--              **rule 축으로 쓰지 않는다** — 매수 주문(19:50)보다 뒤에 굽히므로 사후 정보다.
--              확장 관측 기록 + 소급 백필 적재 대상.
--   거래소별로 슬롯을 나누지 않았다: NXT 매수(19:50)도 14:30 값을 쓴다. 원장이 rule 하나를
--   거래소별로 쪼개 채점하지 못하므로(전 rule 이 exit_label='exec_leg_ret' 공용) 선정과 채점이
--   같은 값을 보는 쪽을 택했다 — 축의 의미는 '14:30 시점 시장 상태'로 일관된다.
--
-- 기존 32행(2026-07-06~08-20)은 19:50 회차 값이므로 slot='1950' 으로 이관한다.
-- source: 'live'=수집 당시 실측 / 'backfill'=일봉 소급 복원 / 'repaired'=결함 값 정정.
--   복원값과 실측값이 같은 컬럼에 섞이므로 구분이 없으면 사후 감사가 불가능하다.

ALTER TABLE market_snapshot
    ADD COLUMN slot VARCHAR(8) NOT NULL DEFAULT '1950'
        COMMENT '스냅샷을 굽는 시각 — 1430(rule 축)/1950(관측·백필)' AFTER snapshot_date,
    ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'live'
        COMMENT 'live=실측 / backfill=일봉 소급 복원 / repaired=결함 값 정정',
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (snapshot_date, slot);
