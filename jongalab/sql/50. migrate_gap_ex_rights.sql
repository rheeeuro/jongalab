-- 갭 체크 권리락 조정 — 무상증자 권리락일 아침의 '가짜 갭하락'을 걷어낸다.
--
-- [문제]
-- 갭 체크는 전일 실거래가(NXT 19:50 / KRX 15:20)를 기준가로 잡는데, 권리락일 아침의 시세는
-- 이미 배정비율만큼 낮춰진 **권리락 기준가** 위에서 형성된다. 그래서 그 종목만 배정비율이
-- 그대로 갭하락으로 찍힌다(리포트·승패 캘린더·텔레그램 알림 전부).
--   2026-08-05 알테오젠(8/4 리포트 1등) 실측: 기준가 346,500 → 08:03 NXT 286,000 = -17.46% 저장.
--   실제로는 권리락 기준가 266,538(=346,500/1.3) 대비 **+7.30% 상승**한 날이다.
--
-- [해법] 권리락 기준가 = 전일 종가 / (1 + 1주당 신주 배정 주수) 로 기준가를 되돌려 계산한다.
-- 배정비율은 ex_rights_schedule(sql/48)의 `ratio` — source='dart' 행이면 DART 확정값이다.
-- 비율을 모르는 추정 행(source='inferred', ratio NULL)은 **조정하지 않는다**: 그 행은 권리락일
-- 자체가 불확실해서 공시일 +1·+2영업일을 둘 다 등록해 둔 것이라, 잘못 조정하면 권리락이 아닌
-- 날의 정상 갭을 망친다(gap_check 이 로그 경고만 남긴다).
--
-- [이 컬럼의 의미] '그날 이 종목의 갭을 권리락 조정해 계산했다'는 표시(NULL = 권리락 아님).
-- 리포트 상세 화면이 조정 기준가를 함께 보여주는 데 쓰고, 엣지 연구에서 이 행을 골라내거나
-- 빼는 데도 쓴다 — 실매매는 권리락일 종목을 아예 매수하지 않으므로(trading/core/ex_rights.py),
-- 조정된 gap_*_pct 는 '그날 주가가 실제로 어떻게 움직였나'를 보는 표시·연구용 값이다.
-- (실집행 라벨 exec_leg_ret·nxt_open_ret 은 지금처럼 outcome_backfill 의 권리락 가드가
--  표본에서 제외한다 — 체결 가능한 거래가 아니었기 때문. 두 계층의 역할이 다르다.)

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS gap_ex_rights_ratio FLOAT DEFAULT NULL
        COMMENT '갭 체크 기준가에 적용한 권리락 배정비율(1주당 신주). NULL=권리락 아님'
        AFTER gap_checked_at;

-- 2026-08-05 알테오젠 정정 — 이미 -17.46% 로 저장·알림된 건을 조정 기준가 대비로 되돌린다.
-- (기준가 = nxt_price_1950 = 그날 갭 체크가 실제로 쓴 19:50 NXT 가격)
UPDATE daily_stock_report
   SET gap_ex_rights_ratio = 0.3,
       gap_nxt_pct = ROUND(
           (gap_nxt_price - ROUND(nxt_price_1950 / 1.3)) / ROUND(nxt_price_1950 / 1.3) * 100, 5)
 WHERE report_date = '2026-08-04'
   AND stock_code = '196170'
   AND gap_nxt_price IS NOT NULL
   AND nxt_price_1950 IS NOT NULL;
