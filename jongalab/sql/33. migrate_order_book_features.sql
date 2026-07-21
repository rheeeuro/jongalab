-- 호가 미시구조 스냅샷 피처 선축적 (2026-07-22, 매수 당시 호가창 저장 — 컬럼만, rule 없음)
--
-- 배경: 재무(sql/32)는 저속 펀더멘털 축이었다. 이 마이그레이션은 정반대 극단인 '초단기
-- 미시구조' 축 — 선정 시점 호가창의 잔량 불균형·스프레드를 저장한다. 호가 불균형(order
-- book imbalance)은 오버나이트 갭 방향에 대한 단기 신호로, 이 시스템에서 엣지가 검증돼 온
-- 흐름/수급 축과 결이 맞는다(재무와 달리 전략 성격에 부합).
--
-- 데이터 소스: 키움 ka10004(주식호가요청) 신규 엔드포인트 — kiwoom 서버 market.py 믹스인 +
-- /stock/order-book 라우트 + jongalab KiwoomRestClient.get_stock_order_book 로 배선.
-- closing_bet 선정 시점(13~15시) 후보당 1콜 추가. core.edge_features.order_book_features()
-- 가 응답을 파생 스칼라로 굽는다(원본 10호가 통째 저장은 노이즈·용량이라 지양).
--
--   ob_imbalance     — 총매수잔량 ÷ 총매도잔량(>1 매수 우위). 핵심 신호.
--   ob_fpr_imbalance — 매수최우선잔량 ÷ 매도최우선잔량(1호가 압력).
--   ob_spread_pct    — (매도1호가 − 매수1호가) ÷ 현재가 × 100(체결비용·유동성).
--
-- 타이밍 특성(중요): 실제 매수는 종가(15:30 단일가)인데 선정 워커는 13~15시 연속장 중 30분
--   주기로 돈다. 호가는 연속장 중에만 유효(장 종료·개장 전엔 잔량이 전부 0 → 파생값 None).
--   repository 가 ob_* 를 PRESERVE_ON_NULL 로 다뤄, 세션 중 마지막 실행(종가 직전 ~15시)이
--   last-write-wins 로 남고 장 종료 후 재실행의 NULL 은 무시한다 → 근사 '매수 당시' 스냅샷.
--   시차(선정 시점 ≠ 종가 체결)를 라벨 해석 시 감안한다.
--
-- ★ rule 은 의도적으로 미등록(데이터부터 축적): 표본이 쌓인 뒤 호가 불균형/스프레드가
--   오버나이트 라벨을 예측하는지 채점하고 candidate rule 을 등록한다. 선정 시점 수집
--   컬럼이라 core.edge_policy.SELECTION_TIME_COLS 에 이미 포함(향후 live 승격 실행 가능).

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS ob_imbalance FLOAT DEFAULT NULL
        COMMENT '총매수잔량÷총매도잔량(>1 매수우위) — core.edge_features.order_book_features' AFTER fin_net_income,
    ADD COLUMN IF NOT EXISTS ob_fpr_imbalance FLOAT DEFAULT NULL
        COMMENT '매수최우선잔량÷매도최우선잔량(1호가 압력)' AFTER ob_imbalance,
    ADD COLUMN IF NOT EXISTS ob_spread_pct FLOAT DEFAULT NULL
        COMMENT '(매도1호가−매수1호가)÷현재가 %(체결비용·유동성)' AFTER ob_fpr_imbalance;
