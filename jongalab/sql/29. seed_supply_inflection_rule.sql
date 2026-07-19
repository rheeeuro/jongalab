-- 수급 변곡점 가설 시드 (2026-07-19, 수급매매 용어 PDF — 신규 컬럼 없음, 시드 전용)
--
-- 통설: "기관·외인이 매도를 이어가던 포지션에서 매수로 전환 + 강한 거래량 동반 상승".
-- 기존 컬럼 근사 — supply_days==1(ka10131 연속 순매수 첫날 = 전환일) + vol_ratio(당일
-- ÷20일 평균 거래량) + 양전. '직전 연속 매도' 엄밀 판정 피처는 만들지 않는다(근사 우선,
-- 유의미하면 그때 정밀화).
--
-- ★ 사전 점검 (2026-07-19, 6/26~7/18 유니버스 재현, 참고용 — 승격 근거 아님):
--   기준선 +0.18%(n=345). vol_ratio>=3 은 **매칭 0**(빈도 부족으로 등록 전 완화) →
--   vol_ratio>=2 로 고정: n=5/3일 +1.92% 승률 80%(표본 극소).
--   supply_days==1 & 양전 전체(거래량 무관)는 n=28 −0.65%·승률 42.9% — 거래량 필터가
--   가설의 핵심 변별이라는 방증. 저빈도(월 ~9건 전망)라 min_sample 40 도달 수개월 소요.

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('f5_supply_inflection', '수급 변곡점', 'f5_supply', 'selector',
 '수급 변곡점(트레이더 칼럼 용어): 기관·외인 연속 순매수 첫날(supply_days==1, 매도→매수 전환일) + 평소 대비 2배 이상 거래량 + 상승 마감은 포지션 방향을 바꾼 주체가 다음날도 이어 산다는 양의 가설. 사전 점검(6/26~7/18 인샘플, 참고용): vol_ratio>=3 매칭 0으로 등록 전 >=2 완화 — n=5/3일 +1.92%·승률 80%(표본 극소), 거래량 무관 전체는 −0.65%·42.9%라 거래량 필터가 핵심 변별. 저빈도 rule — out-of-sample 로 판정.',
 '[{"col":"supply_days","op":"==","value":1},{"col":"vol_ratio","op":">=","value":2},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
