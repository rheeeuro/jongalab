-- 수급 눌림 rule 1음봉/2음봉 분리 + 매수(selector) 전환 (2026-07-19 — sql/23 등록 당일 정정)
--
-- 배경: sql/23 은 눌림을 f5_frgn_surge_pullback(서지 후 1~2일 + 당일 음봉, benchmark) 하나로
-- 묶었다. 등록 당일(피처 축적 전, 표본 0) 사용자 정정 — PDF 통설 원 의미("수급 1음봉"과
-- "수급 2음봉"은 별개 진입 자리)대로 두 rule 로 나누고 매수(selector) rule 로 등록한다.
-- ma5_reclaim(sql/21) 전례와 같은 표본 0 시점 정정이라 사전 등록 원칙 위반 아님.
--
--   red_candle_streak — 당일 포함 연속 음봉 수(당일 양봉이면 0). "2음봉"을 전일 봉색까지
--                       보고 판정하기 위한 피처(red_candle 은 당일만 본다).
--                       추가 API 콜 0 — 기존 일봉(ka10081) 6봉에서 파생.
--
-- ★ 사전 점검 (2026-07-19, 6/26~7/18 유니버스 재현, 참고용 — 승격 근거 아님):
--   기준선 +0.18%(n=345).
--   수급 1음봉(서지 D-1 + 당일 음봉):          n=55/8일 +0.22% 승률 52.7% t=0.53 — 기준선 수준.
--   수급 2음봉(서지 D-2 + 전일·당일 연속 음봉): n=8/4일  +0.50% 승률 50.0% — 표본 극소
--     (전일 유니버스 부재로 10건 판정 불가 — 라이브 피처는 일봉 기반이라 커버리지 문제 없음).
--   관찰 메모: 서지 D-2 + 당일 음봉인데 전일 양봉(쉬었다 반락)은 n=22 −1.16% 승률 22.7%
--   t=−1.99 — 눌림이 아니라 반락 시작일 가능성. 표본 쌓이면 veto 후보로 별도 등록 검토.
--
-- selector 주의: 음봉 매칭 표본 대부분이 음전이라, live 승격돼도 실효 집행은
-- 음봉+양전(갭업 후 밀림) 부분집합에 한정된다(선정 레이어가 음전 후보를 핸드오프 제외).
-- 승격 판단 시 이 점을 감안할 것.

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS red_candle_streak TINYINT DEFAULT NULL
        COMMENT '당일 포함 연속 음봉 수(당일 양봉=0) — core.edge_features.red_candle_streak' AFTER red_candle;

-- 등록 당일·표본 0 인 통합 rule 제거(정정 재등록 — 축적 표본이 있었다면 삭제 불가였다)
DELETE FROM edge_rule WHERE name = 'f5_frgn_surge_pullback' AND status = 'candidate';

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES

('f5_frgn_surge_pullback1', '수급 1음봉', 'f5_supply', 'selector',
 '수급 1음봉 종가매수(트레이더 칼럼 통설): 외인 대량 순매수(>=100억) 바로 다음 거래일의 첫 음봉 조정은 미처 못 담은 수급 주체가 익일 이어 사는 눌림 자리라는 양의 가설. sql/23 통합 rule(f5_frgn_surge_pullback, benchmark)의 등록 당일 표본 0 시점 분리 정정 — 1음봉/2음봉은 별개 진입 자리. 사전 점검(6/26~7/18 인샘플, 참고용): n=55/8일, next_open_ret +0.22%·승률 52.7% vs 기준선 +0.18% — 기준선 수준, out-of-sample 로 판정. 주의: 음봉 표본 대부분이 음전이라 live 승격 시 실효 집행은 음봉+양전(갭업 후 밀림)에 한정.',
 '[{"col":"days_since_frgn_surge","op":"==","value":1},{"col":"red_candle","op":"==","value":1}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

('f5_frgn_surge_pullback2', '수급 2음봉', 'f5_supply', 'selector',
 '수급 2음봉 종가매수(트레이더 칼럼 통설): 외인 대량 순매수(>=100억) 후 이틀 연속 음봉(전일·당일, red_candle_streak>=2)까지 눌린 자리는 분할 매수 2차 진입점이라는 양의 가설 — 1음봉(f5_frgn_surge_pullback1)과 별개 자리. 사전 점검(6/26~7/18 인샘플, 참고용): n=8/4일, next_open_ret +0.50%·승률 50.0% — 표본 극소(전일 커버리지 한계, 라이브 피처는 일봉 기반이라 무관), out-of-sample 로 판정. 관찰 메모: 같은 D-2 라도 전일 양봉 후 당일 음봉(쉬었다 반락)은 인샘플 −1.16%(t=−1.99)로 나빠 predicate 에서 연속 음봉만 잡는다. 주의: 음봉 표본 대부분이 음전이라 live 승격 시 실효 집행은 음봉+양전에 한정.',
 '[{"col":"days_since_frgn_surge","op":"==","value":2},{"col":"red_candle_streak","op":">=","value":2}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
