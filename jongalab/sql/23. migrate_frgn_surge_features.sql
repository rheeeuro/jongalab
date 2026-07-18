-- 외인 서지 후 눌림/지속 피처 + 대칭 쌍 가설 시드 (2026-07-19, 종가베팅 팁 PDF 검토 후속)
--
-- 배경: "외인 대량 유입일 뒤 1~2일 음봉에서 종가 매수(수급 1음봉/2음봉)" 통설(트레이더 칼럼)을
-- 실험실 검증 대상으로 올린다. sql/20·22 의 레벨 축과 같은 방식 — 한 축(서지 후 1~2일)을
-- 음봉(눌림)/비음봉(지속) 대칭 쌍으로 갈라 손익 분기를 데이터가 판정하게 한다.
-- 추가 API 콜 0 — supply_history(ka10059, 기수집)와 일봉(ka10081, 기수집)에서 파생
-- (core.edge_features.days_since_frgn_surge / red_candle 순수 함수).
--
--   days_since_frgn_surge — 직전 거래일 중 외인 순매수 >= 100억(서지)이 있었던 가장 가까운
--                           날의 경과 거래일 수(1=어제, 최대 4). 당일 서지는 세지 않는다
--                           (당일 유입은 frgn_net_buy 가 이미 본다). 서지 없음 → NULL.
--                           임계 100억은 수급 정규화 구간 경계와 동일 스케일 — 변경은
--                           새 컬럼·rule 재등록으로만(사전 등록 원칙).
--   red_candle            — 당일 음봉(현재가 < 당일 시가) 여부. 음전(change_pct<0)과 다른
--                           정보 — 갭업 후 밀린 날은 상승 마감이어도 음봉.
--
-- ★ 사전 점검 (2026-07-19, 6/26~7/18 유니버스 재현 — supply_history·09시봉 시가로
--   선정 시점 계산과 동일 재료, 참고용 — 승격 근거 아님): 기준선 +0.18%(n=345).
--   서지(100억) 후 1~2일 전체:  n=140/11일 next_open_ret +0.61% 승률 55.0% t=1.63
--   └ 눌림(+음봉):             n=77/8일  −0.18% 승률 44.2% t=−0.51 — 통설과 달리 인샘플 약음
--   └ 지속(비음봉, change>=0): n=61/9일  +1.47% 승률 67.2% t=2.03 — 인샘플 강양
--   축이 인샘플에서 이미 갈린다 — out-of-sample 이 판정한다.

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS days_since_frgn_surge TINYINT DEFAULT NULL
        COMMENT '외인 서지(순매수>=100억) 후 경과 거래일(1=어제, 최대4, 당일 제외) — core.edge_features.days_since_frgn_surge' AFTER ma5_reclaim,
    ADD COLUMN IF NOT EXISTS red_candle TINYINT DEFAULT NULL
        COMMENT '당일 음봉(현재가<당일 시가) 여부 — core.edge_features.red_candle' AFTER days_since_frgn_surge;

-- ★ 사전 등록 원칙: 임계값은 등록 시점 고정, 조정은 '새 rule 재등록'으로만.
--   피처 축적은 다음 closing_bet 실행부터 — 그 이전 날짜는 NULL=매칭 실패로 자연 제외.

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES

-- 눌림(PDF 통설) — role=benchmark: 음봉 표본 대부분이 음전이라 live selector 로는 무의미
-- (_apply_selection 이 음전 후보를 핸드오프에서 제외). 측정 전용으로 축적하고,
-- 양(+) 확정 시 집행 설계(음전 제외) 재검토 후 selector 재등록, 음(−) 확정 시 veto 재등록 후보.
('f5_frgn_surge_pullback', '외인 서지 후 음봉 눌림', 'f5_supply', 'benchmark',
 '수급 눌림 종가매수 통설(트레이더 칼럼 "수급 1음봉/2음봉"): 외인 대량 순매수(>=100억) 다음 1~2거래일의 음봉 조정은 미처 못 담은 수급 주체가 익일 이어 사는 눌림 자리라는 양의 가설. 사전 점검(6/26~7/18 인샘플, 참고용): n=77/8일, next_open_ret −0.18%·승률 44.2% vs 기준선 +0.18% — 통설과 달리 약음(유의성 없음). 음봉 표본은 대부분 음전이라 live 선정 불가(음전 핸드오프 제외) → benchmark 측정 전용. 음(−) 확정 시 veto 재등록 후보, 양(+) 확정 시 집행 설계 재검토.',
 '[{"col":"days_since_frgn_surge","op":"between","value":[1,2]},{"col":"red_candle","op":"==","value":1}]',
 'exec_leg_ret', 'candidate', 40, CURDATE()),

-- 지속(대칭 쌍) — role=selector: 서지 후 조정 없이 이어가는 종목은 못 채운 외인 수요가
-- 익일로 이월된다는 양의 가설. 전 컬럼 선정 시점 계산이라 검증 시 live 승격 가능.
('f5_frgn_surge_carry', '외인 서지 후 지속', 'f5_supply', 'selector',
 '수급 지속 이월 매수자: 외인 대량 순매수(>=100억) 다음 1~2거래일에 음봉 없이(비음봉·상승 유지) 버티는 종목은 포지션을 하루에 못 채운 외인·후발 수급이 익일 아침 이어 산다는 양의 가설 — f5_frgn_surge_pullback(눌림, 통설)의 대칭 쌍으로 같은 축의 손익 분기를 데이터로 가른다. f5_inst_frgn_dual_buy(당일 동반 순매수)와 달리 당일 수급이 아니라 직전 서지의 이월을 본다. 사전 점검(6/26~7/18 인샘플, 참고용): n=61/9일, next_open_ret +1.47%·승률 67.2%·t=2.03 vs 기준선 +0.18% — out-of-sample 로 판정.',
 '[{"col":"days_since_frgn_surge","op":"between","value":[1,2]},{"col":"red_candle","op":"==","value":0},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
