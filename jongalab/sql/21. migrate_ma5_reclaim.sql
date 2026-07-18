-- 5일선 재탈환 피처 + 가설 시드 (2026-07-19, 사용자 제안 가설)
-- (등록 당일 정정: 최초안의 '전일 음봉' 조건은 표본 축적 전(첫 캡처 7/21) 사용자 정정으로
--  제거 — 이탈 '봉 색'이 아니라 이탈 '위치'가 가설의 본질. 표본 0 시점 정정이라 사전 등록
--  원칙 위반 아님. 이 파일은 정정 반영 최종본이며 멱등(재실행 안전)이다.)
--
-- 가설: "5일선 밑에 있다가 5일선을 뚫는 강한 양봉" — 단기 조정(5일선 이탈) 후 강한 양봉으로
-- 5일선을 회복하면, 조정 종료 신호로 읽는 눌림목·추세추종 매수자가 익일 아침 따라붙는다.
--
-- 피처 ma5_reclaim (core.edge_features, 추가 API 콜 0 — 기존 일봉 1콜에서 시가·종가 파싱):
--   ① 전일 종가 < 전일 MA5  ② 당일 양봉(현재가>시가)  ③ 현재가 > 당일 MA5(현재가 포함).
--   이력 6봉 미만·장 전이면 NULL.
--   '강한'은 predicate 의 change_pct 밴드로 분리해 임계값을 룰에 명시적으로 남긴다.
--
-- ★ 사전 점검 (2026-07-19, 참고용 — 승격 근거 아님, lab README §5-1):
--   6/26~7/15 유니버스 재현(당일 종가 근사) — 매칭 n=33/7거래일(일 1~11건, 빈도 충분),
--   next_open_ret mean −0.44%·승률 45.5% vs 나머지 유니버스 +0.25%·52.2%.
--   인샘플 무엣지(음의 방향이나 표본 소·유의성 없음) — out-of-sample 표본이 판정한다.

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS ma5_reclaim TINYINT DEFAULT NULL AFTER round_dist_pct;
ALTER TABLE daily_stock_report
    MODIFY COLUMN ma5_reclaim TINYINT DEFAULT NULL COMMENT '5일선 재탈환(전일 5일선 아래 → 당일 5일선 위 양봉) — core.edge_features.ma5_reclaim';

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('f5_ma5_reclaim', '5일선 재탈환', 'f5_supply', 'selector',
 '눌림목 반등 확인 매수자: 단기 조정(전일 종가가 5일선 아래) 뒤 강한 양봉(+3%~15%)으로 5일선을 재탈환하면, 조정 종료 신호로 읽는 눌림목·추세추종 매수자가 익일 아침 진입한다는 양의 가설(2026-07-19 사용자 제안, 등록 당일 표본 0 시점에 전일 음봉 조건 제거 정정). 사전 점검(6/26~7/15 인샘플 재현, 참고용): n=33, next_open_ret −0.44%·승률 45.5% vs 유니버스 +0.25%·52.2% — 무엣지(음의 방향, 유의성 없음), out-of-sample 로 판정.',
 '[{"col":"ma5_reclaim","op":"==","value":1},{"col":"change_pct","op":"between","value":[3,15]}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());

-- 정정 반영 (INSERT IGNORE 는 기존 행을 안 건드리므로 별도 UPDATE — 재실행 멱등)
UPDATE edge_rule SET
  title = '5일선 재탈환',
  description = '눌림목 반등 확인 매수자: 단기 조정(전일 종가가 5일선 아래) 뒤 강한 양봉(+3%~15%)으로 5일선을 재탈환하면, 조정 종료 신호로 읽는 눌림목·추세추종 매수자가 익일 아침 진입한다는 양의 가설(2026-07-19 사용자 제안, 등록 당일 표본 0 시점에 전일 음봉 조건 제거 정정). 사전 점검(6/26~7/15 인샘플 재현, 참고용): n=33, next_open_ret −0.44%·승률 45.5% vs 유니버스 +0.25%·52.2% — 무엣지(음의 방향, 유의성 없음), out-of-sample 로 판정.'
WHERE name = 'f5_ma5_reclaim';
