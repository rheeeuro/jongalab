-- 권리락 예정일 캘린더 — trading signal_executor 가 읽기 전용 조회해 **매수를 건너뛴다**.
-- (jongalab 이 판정을 적재하고 trading 이 읽는 단방향 패턴 — news_veto_verdict·macro_event 와 동일)
--
-- [왜 필요한가]
-- 무상증자 권리락일에는 기준가가 배정비율만큼 기계적으로 낮아진다(1주당 0.3주 배정 → -23%).
-- 종가베팅은 '오늘 종가 매수 → 익일 시가 매도'라, **익일이 권리락일이면** 그 조정폭이 그대로
-- 실현손실로 찍힌다. 공짜 신주는 신주 상장일(보통 3주 뒤)에나 들어오고, 1주만 산 경우엔
-- 단수주라 주식이 아니라 현금으로 나온다 — 즉 그 자리에서 상계되지 않는다.
--   2026-08-04 알테오젠(1등 종목) 실사례: 종가 346,500 → 익일 기준가 267,000(-23%).
--   1주 346,500원 매수 시 약 -79,500원이 손실로 확정되고, 보전분 8만원은 8/26 입금.
-- 검증된 엣지(종가→익일시가)와 성격이 다른 거래이므로 **아예 매수하지 않는다**.
--
-- [권리락일을 어떻게 아는가]
-- 거래소 '권리락' 공시일로는 판정할 수 없다 — 공시일→권리락일 간격이 종목마다 다르다
-- (알테오젠 8/4 공시→8/5 권리락 / 대동기어 7/31 공시→8/4 권리락).
-- DART 무상증자 결정 상세(fricDecsn)의 **신주배정기준일**(nstk_asstd)이 유일한 정확한 근거이고,
--   권리락일 = 신주배정기준일의 **직전 영업일**
-- 이 규칙은 실측 3건으로 확인했다(2026-08-04):
--   알테오젠 기준일 8/6 → 권리락 8/5 | 유진테크놀로지 7/30 → 7/29 | RF머트리얼즈 7/27 → 7/24
-- 배정비율은 종목마다 다르다(실측 0.2 / 0.3 / 1.0) — 스킵 판단에는 쓰지 않고 추적용으로 남긴다.
--
-- [채우는 시점] disclosure_collector 가 트리거 2개로 채운다(둘 다 같은 fricDecsn 조회):
--   1) 무상증자 결정 공시 — 보통 권리락 2~3주 전. 정상 경로.
--   2) 거래소 권리락 공시 — 결정 공시를 놓친 종목(수집 시작 전 결정분 등)의 보완 경로.
--      권리락 1~2영업일 전에 오므로 NXT 19:30 매수는 막을 수 있다(KRX 15:20 은 공시가 16:50
--      도착이라 이 경로로는 못 막는다 → 결정 공시 경로가 정상 커버).
--
-- [source='inferred' 폴백이 왜 필요한가]
-- fricDecsn 은 **주요사항보고서(무상증자결정)** 기반이라, 무상증자를 자율공시로만 낸 종목은
-- 조회에 아무것도 없다(2026-08-04 뉴로메카 실측: status 013 '데이터 없음'). 그러면 정확한
-- 기준일을 얻을 수 없는데, 그렇다고 매수를 그냥 통과시키면 이 캘린더의 목적이 무너진다.
-- 그래서 권리락 공시를 본 이상 **공시일 직후 2영업일을 권리락 가능일로 추정 등록**한다
-- (실측 간격이 +1영업일(알테오젠)·+2영업일(대동기어)로 갈렸으므로 둘 다 덮는다).
-- 과잉 차단(며칠간 그 종목 매수 기회 상실)을 감수하는 쪽을 택한 이유는 목표가 '잃지 않고
-- 꾸준히'이고, 빈도가 월 1~2건이라 기회비용이 작기 때문이다. 정확한 건(source='dart')이
-- 나중에 들어오면 그 행이 따로 생기고, 추정 행은 지난 날짜가 되어 자연히 조회에서 빠진다.

CREATE TABLE IF NOT EXISTS ex_rights_schedule (
    ticker         VARCHAR(12)   NOT NULL COMMENT '종목코드(6자리, 접미사 없음)',
    ex_rights_date DATE          NOT NULL COMMENT '권리락일 = 신주배정기준일 직전 영업일 (파생)',
    record_date    DATE              NULL COMMENT '신주배정기준일 (DART nstk_asstd). inferred 면 NULL',
    ratio          DECIMAL(10,4)     NULL COMMENT '1주당 신주 배정 주수 (추적용 — 스킵 판단에 미사용)',
    listing_date   DATE              NULL COMMENT '신주 상장 예정일 (보전분 입금 시점 추적용)',
    source         VARCHAR(12)   NOT NULL DEFAULT 'dart'
                   COMMENT 'dart=fricDecsn 기준일로 확정 / inferred=권리락 공시일 기반 추정(과잉 차단)',
    source_key     VARCHAR(32)   NOT NULL COMMENT 'DART 접수번호(결정 공시 또는 권리락 공시)',
    corp_name      VARCHAR(80)       NULL,
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, ex_rights_date),
    KEY idx_ex_rights_date (ex_rights_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='권리락 예정일 — trading 이 익일 권리락 종목 매수를 건너뛴다';

-- 2026-08-05 권리락 2건 시드 — 도입 당일 건이라 수집기 트리거보다 앞선다(결정 공시가
-- 수집 시작 전이었고 권리락 공시는 당일 16:50 도착). 값은 DART fricDecsn 실조회분.
INSERT INTO ex_rights_schedule
    (ticker, ex_rights_date, record_date, ratio, listing_date, source, source_key, corp_name)
VALUES
    ('196170', '2026-08-05', '2026-08-06', 0.3000, '2026-08-26', 'dart', '20260720000129', '알테오젠')
    -- 같은 날 권리락인 뉴로메카(348340)는 자율공시 건이라 여기 시드하지 않는다 —
    -- 수집기의 inferred 폴백이 실제 접수번호로 채운다(다음 주기 08:20~20:50, 30분 간격).
ON DUPLICATE KEY UPDATE record_date = VALUES(record_date), ratio = VALUES(ratio),
                        listing_date = VALUES(listing_date), source = VALUES(source),
                        source_key = VALUES(source_key), corp_name = VALUES(corp_name);
