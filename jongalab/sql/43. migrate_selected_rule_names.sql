-- 선정 근거(rule_names)를 daily_stock_report 에도 기록 (2026-07-29)
--
-- 배경: EDGE_SELECTION_MODE=hybrid 가 실운영 중이다. hybrid 는 live selector rule 매칭 종목을
-- **점수 순위와 무관하게** 우선 슬롯에 넣고 남은 자리만 점수순으로 채운다
-- (core.edge_selection.select_signals). 실제로 2026-07-29 선정 10건에는 기아(점수 35위)·
-- 신한지주(62위)가 f5_prog_persistent 매칭으로 들어왔다 — 점수만으로는 절대 못 들어올 종목이다.
--
-- 문제: 그 '선정 근거'는 trading DB 의 trade_signal.rule_names 에만 저장됐다. jongalab 쪽
-- daily_stock_report 에는 컬럼이 없어서, 종목 탭·리포트 화면이 **왜 이 종목이 목록에 있는지**
-- 알 방법이 없었다. 점수 62위 종목이 표시 순번상 "10위"로 보이니 점수로 뽑힌 것처럼 읽힌다.
--
-- 해결: closing_bet 이 이미 손에 들고 있는 rule_names_by_code 를 selected 와 같은 자리에서
-- 리포트 행에도 태깅한다(_apply_selection). 프론트는 이 값으로 '룰 선정' 배지 + 실제 점수
-- 순위를 함께 보여주고, 배지에서 /lab/<rule> 로 넘어갈 수 있다.
--
-- upsert 정책: selected 와 **완전히 같이 움직여야 한다**. closing_bet 은 08:00~20:30 매 30분
--   재실행되며 매 실행이 selected 를 처음부터 다시 판정하므로, rule_names 도 매번 덮어써야
--   한다(PRESERVE_ON_NULL 대상 아님). legacy 폴백 실행이 NULL 로 덮는 것이 정상 동작이다 —
--   그 실행의 선정은 실제로 점수 기반이었기 때문이다.
--
-- 값 형식: 매칭된 live selector rule 의 name 콤마 목록(예 'f5_prog_persistent').
--   NULL = 점수순으로 들어온 종목(legacy 모드 전체 / hybrid 의 잔여 슬롯) 또는 비선정 후보.
--   veto rule 은 제외만 하므로 여기 남지 않는다(제외된 종목은 selected=0).

ALTER TABLE daily_stock_report
    ADD COLUMN IF NOT EXISTS rule_names VARCHAR(255) DEFAULT NULL
        COMMENT '선정 근거 edge_rule name 콤마 목록(hybrid/rules 모드) — NULL=점수순 선정 또는 비선정'
        AFTER selected;

-- 확인
SELECT report_date, rank_no, stock_name, score, selected, rule_names
  FROM daily_stock_report
 WHERE report_date = CURDATE() AND selected = 1
 ORDER BY rank_no;
