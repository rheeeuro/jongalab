-- 프로그램 장중 오전/오후 분해 피처 + 전환 가설 시드 (2026-07-19, 종가베팅/매물대 PDF 후속)
--
-- 배경: 트레이더 칼럼 2편이 공통으로 "오전 프로그램 매도 출회 → 오후 프로그램 매수 전환"
-- 을 종가매매 진입 신호로 선호한다(레인보우로보틱스 사례). 일별 prog_net_buy 는 실측
-- 역효과(2026-07-03, 갭 승률 9.1%)로 가점이 제거됐지만, 그건 '하루 합계'였고 이 축은
-- '일중 방향 전환'이라 별개 신호다 — 검증 대상으로 올린다.
--
-- 데이터: ka90008(종목시간별프로그램매매, 통합 SOR) 틱 시계열 — 이번에 kiwoom 서버
-- 엔드포인트(/program-trade/hourly-trend)로 신규 노출(구 구현은 URI 버그로 미사용).
--
-- 수집 방식 = 2점 스냅샷 차분(실측 2026-07-19 재설계): 틱 워킹으로 12:00 경계까지
-- 거슬러 올라가는 방식은 유동 종목에서 비현실적(삼성전자 12:00~14:30 구간만 11,256틱
-- ≈ 57페이지). 대신 30분 주기 closing_bet 재실행을 이용한다 — 후보당 1페이지(최신 누적)만:
--   · 정오 창(12:00~12:45) 실행 → 현재 누적을 prog_am_net 으로 저장(첫 기록 보존)
--   · 오후 창(12:45~15:35) 실행 → prog_pm_net = 현재 누적 − 저장된 정오 누적
--   · 창 밖 실행은 스킵 — 키움이 당일 데이터 없으면(개장 전·휴장) 최근 거래일을 폴백
--     반환하므로 오염 방지. 최신 행 tm 가드(09:00~15:35)도 이중으로 건다.
--   · repository upsert: prog_am_net 은 first-write-wins, prog_pm_net 은 NULL 무시 —
--     창 밖 재실행이 유효 캡처를 지우지 않는다.
--
--   prog_am_net — 정오 창 실행 시점(≈12:00)의 당일 프로그램 누적 순매수(원)
--   prog_pm_net — 오후 실행 시점 누적 − 정오 누적 = 오후 순유입(원)
--
-- ★ 사전 점검 불가: 틱 시계열은 저장해 둔 이력이 없어 인샘플 재현이 불가능하다 —
--   초기 시드 rule 들(sql/8)과 같은 순수 out-of-sample 검증. 첫 캡처는 다음 거래일부터.

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS prog_am_net BIGINT DEFAULT NULL AFTER poc_dist_pct,
    ADD COLUMN IF NOT EXISTS prog_pm_net BIGINT DEFAULT NULL AFTER prog_am_net;
ALTER TABLE daily_stock_report
    MODIFY COLUMN prog_am_net BIGINT DEFAULT NULL
        COMMENT '정오 창(12:00~12:45) 실행 시점 프로그램 누적 순매수(원, 스냅샷) — core.edge_features.prog_cum_net',
    MODIFY COLUMN prog_pm_net BIGINT DEFAULT NULL
        COMMENT '오후 실행 누적 − 정오 누적 = 오후 프로그램 순유입(원) — closing_bet 2점 스냅샷 차분';

-- ★ 사전 등록 원칙: 임계값은 등록 시점 고정, 조정은 '새 rule 재등록'으로만.

INSERT IGNORE INTO edge_rule
  (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES
('f5_prog_pm_reversal', '프로그램 오후 전환', 'f5_supply', 'selector',
 '프로그램 오후 전환 매수자(트레이더 칼럼 통설): 오전에 프로그램 매도가 출회됐다가(prog_am_net<=0) 오후에 순매수로 전환(prog_pm_net>0)한 종목은 바스켓·차익 자금이 오후 방향을 바꿔 담기 시작한 것이라 익일 아침까지 이어진다는 양의 가설. 일별 프로그램 순매수 가점은 2026-07-03 실측 역효과로 제거됐으나 그건 하루 합계 — 이 rule 은 일중 방향 전환이라 별개 축. 사전 점검 불가(틱 이력 미저장, 순수 out-of-sample 검증) — 첫 캡처는 등록 다음 거래일부터.',
 '[{"col":"prog_am_net","op":"<=","value":0},{"col":"prog_pm_net","op":">","value":0},{"col":"change_pct","op":">=","value":0}]',
 'exec_leg_ret', 'candidate', 40, CURDATE());
