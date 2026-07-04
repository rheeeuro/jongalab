-- 결과 라벨 다중화 (Phase 2, 2026-07-04)
-- 목적: 청산 타이밍이 실측 최대 레버(08:03 vs 08:05 = +0.35%)인데 결과 라벨이 next_open_ret
--       하나뿐이라 rule 별 최적 청산창을 비교할 수 없다. 라벨을 1 → 5개로 늘려 하루의
--       표본 정보량을 다중화한다(물리 제약 ④ 우회). 매매 행위에 영향 0 — 순수 관측·기록.
--
-- 앵커 통일: 연구 라벨의 분모는 전부 KRX 확정 종가(Phase 1 krx_close_price, 없으면 일봉 종가).
--   실집행 창 재현용 기존 gap_* 컬럼은 앵커가 다르지만(19:50 NXT) 그대로 존치 — 용도가 다르다.
--
-- 일봉 백필 라벨 3종(outcome_backfill 이 같은 일봉 1회 조회에서 파생 — 추가 API 콜 0, 과거 소급 가능):
--   next_high_ret  — 종가→익일 고가(장중 최대 실현 가능치. 일봉 고가엔 VI·단일가 왜곡 섞일 수 있어 "이론상 최대"로만 해석)
--   next_low_ret   — 종가→익일 저가(꼬리 리스크·하드 손절 관통 측정. veto·리스크 연구 핵심)
--   next_close_ret — 종가→익일 종가(홀드 시나리오)
-- 실시간 수집 라벨 2종(gap_check --label-nxt 08:06, 유니버스 전체. 소급 불가 — 배포일부터 축적):
--   nxt_open_price — 익일 08:06 NXT 가격
--   nxt_open_ret   — KRX 확정 종가(krx_close_price)→익일 08:06 NXT 등락률. 체결 가능 시각 스냅샷이라
--                     청산창 실측은 이 라벨을 next_high/low(이론치)보다 우선

ALTER TABLE daily_stock_report
    ADD COLUMN next_high_ret FLOAT DEFAULT NULL COMMENT '종가→익일 고가 등락률(%) — 장중 최대 실현 가능치(VI/단일가 왜곡 유의)' AFTER next_open_ret,
    ADD COLUMN next_low_ret FLOAT DEFAULT NULL COMMENT '종가→익일 저가 등락률(%) — 꼬리 리스크(스톱 관통 측정)' AFTER next_high_ret,
    ADD COLUMN next_close_ret FLOAT DEFAULT NULL COMMENT '종가→익일 종가 등락률(%) — 홀드 시나리오' AFTER next_low_ret,
    ADD COLUMN nxt_open_price INT DEFAULT NULL COMMENT '익일 08:06 NXT 가격(유니버스 전체)' AFTER next_close_ret,
    ADD COLUMN nxt_open_ret FLOAT DEFAULT NULL COMMENT 'KRX 확정 종가→익일 08:06 NXT 등락률(%)' AFTER nxt_open_price;
