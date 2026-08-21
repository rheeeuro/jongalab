-- 2026-08-21 야간선물 축 측정 rule 2종 시드 (NXT 한정, 페이퍼 전용 benchmark)
--
-- 재는 것: **NXT 매수 시점(19:50)의 코스피200 야간선물 방향이 익일 시가 수익을 가르는가.**
-- 실측 근거(관측 슬롯 32일 창, 유니버스 평균 next_open_ret): r=+0.356 · t=+2.05 — 지금까지
-- 재본 축 중 가장 강한 **순방향** 신호이지만 표본 미달이라 켤 수 없다. 근거·기각 이력은
-- docs/history/gates-sizing.md · edge-ledger.md 2026-08-21.
--
-- 왜 사후 분석이 아니라 rule 로 등록하나: 사전 등록 원칙(registered_at 이후만 채점) 때문에
-- 지금 등록해야 out-of-sample 표본이 오늘부터 쌓인다. 나중에 등록하면 그때 또 0일부터 시작한다.
--
-- 왜 NXT 한정(nxt_listed=1)인가: 야간세션은 18:00 에 시작하므로 이 축은 **NXT 회차에만 실시간
-- 값이다**. KRX 종가매수(15:20) 시점엔 전일 야간 종가(9시간 전)라 같은 이름의 다른 변수다
-- (그래서 주간 축 목록에서 빼고 EXECUTION_TIME_MARKET_COLS 로 분리했다).
--
-- **선정 시점에 실제로 쓸 수 있다** — 이게 이 rule 설계의 전제다:
--   · `nxt_listed`·`nxt_gap_pct` : closing_bet._fetch_nxt_gap 이 19:40 회차에 실시간으로 재서
--     룰 평가 dict 에 넣는다(f3_nxt_gap_quality 가 live selector 로 도는 것과 같은 경로).
--   · `market.k200f_night_ret`   : gap_check --market-snap-nxt(19:35)가 굽는 슬롯 1935 를
--     closing_bet 19:40 회차가 읽는다(slot_for_now). 채점도 같은 슬롯이다(rule_evaluator).
-- 즉 이 rule 이 통과하면 **그대로 selector 로 승격 가능한 형태**다 — 측정만 되고 못 쓰는
-- 페이퍼로 남지 않는다.
--
-- 왜 두 밴드(하락/그외)인가: 한쪽만 등록하면 "그날 시장이 좋았나"와 구분이 안 된다.
-- 상보적 두 밴드를 나란히 두면 축의 변별력이 바로 보인다(f5_supply_band_* 와 같은 방식).
--
-- **기준가 = 그날 KRX 주간 정산가.** 야간세션 시작(18:00)에 갈아탄다(실측: prev_close 가
-- 8/20 00~05시 1016.25 → 18시 이후 1082.25, 변화율 +6.49% = 그날 k200f_day_ret 과 일치).
-- 그래서 이 값의 뜻은 '**오늘 국장 종가 이후 새로 들어온 정보**'이고, 임계 -0.4%p 도 정산가 대비다.
-- 세션 밖 값은 기준가가 다르므로 스냅샷 단계에서 NULL 처리된다(core/market_data.night_ret_if_fresh).
--
-- 임계 -0.4%p 는 **futures_gate 가 이미 쓰는 하락 판정 밴드**다(FUTURES_FLAT_Z 0.25 ×
-- FUTURES_SD_K200_NIGHT 1.6 — 그 σ 도 같은 정의(정산가 대비)로 측정돼 눈금이 일관된다).
-- 새 눈금을 발명하지 않았다 — 라이브 게이트와 같은 자로 재야 결과를 그 게이트 튜닝에 쓸 수 있다.
--
-- exit_label 은 next_open_ret(익일 정규장 시가 = 실제 청산 시점, 유니버스 전체 커버).
-- exec_leg_ret 을 쓰면 **실제 체결된 종목만** 라벨이 있어 표본이 매매 선정에 편향된다.
--
-- role=benchmark: 지금은 **측정 도구**다(선정에 관여하지 않는다). 두 밴드가 상보적이라 그대로
-- selector 로 켜면 '야간선물 하락일엔 전량 제외' = 총 시드 컷이 되는데, 그 형태는 이미 기각된
-- 설계다(regime_gate 상시컷 — docs/history/gates-sizing.md). 축의 변별력이 확인되면 그때
-- **기존 selector 에 AND 조건으로 붙인 새 rule** 로 재등록한다(사전 등록 원칙).
--
-- INSERT IGNORE 로 재실행해도 기존 행(=registered_at)을 보존한다 — 표본 시작일이 흔들리지 않게.

INSERT IGNORE INTO edge_rule
    (name, title, family, role, description, predicate, exit_label, status, min_sample, registered_at)
VALUES

('f2_night_fut_down_nxt', '야간선물 하락일 · NXT 종목', 'f2_global', 'benchmark',
 '저녁(NXT) 시간대에 살 수 있는 종목 중, 살 때 코스피200 야간선물이 빠져 있던 날만 모아 다음날 아침 성적을 재는 측정용 전략입니다. 야간선물은 오늘 밤 시장 분위기를 실시간으로 보여주는 지표입니다. 이 그룹이 아래 짝 전략보다 성적이 나쁘다면 "밤 분위기가 나쁘면 다음날 아침도 나쁘다"가 확인되고, 그때 기존 매수 전략에 이 조건을 덧붙이게 됩니다.',
 '[{"col":"nxt_listed","op":"==","value":1},{"col":"market.k200f_night_ret","op":"<","value":-0.4}]',
 'next_open_ret', 'candidate', 40, CURDATE()),

('f2_night_fut_up_nxt', '야간선물 보합·상승일 · NXT 종목', 'f2_global', 'benchmark',
 '위 전략의 짝입니다. 같은 저녁 시간대 종목 중 살 때 야간선물이 빠지지 않았던 날만 모아 성적을 잽니다. 두 그룹을 나란히 비교해야 "야간선물이 정말 다음날을 가르는지"와 "그냥 그날 시장이 좋았을 뿐인지"를 구분할 수 있습니다.',
 '[{"col":"nxt_listed","op":"==","value":1},{"col":"market.k200f_night_ret","op":">=","value":-0.4}]',
 'next_open_ret', 'candidate', 40, CURDATE());
