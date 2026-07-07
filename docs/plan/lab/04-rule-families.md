# Phase 3.5 — 초기 가설 카탈로그 (시드 rule 등록)

> Phase 3 배포 직후 등록할 초기 rule 들. 각 rule 은 **인과 근거(누가 왜 내일 아침 사는가)**를
> 갖고, 전부 candidate 로 시작한다(control·veto 제외). 여기 적힌 임계값은 출발점일 뿐이며,
> 등록 후 out-of-sample 표본이 검증한다 — **임계값을 사후에 옮기면 새 rule 로 재등록한다**
> (같은 rule 의 조건을 몰래 튜닝하는 것은 사전 등록 원칙 위반).

## 대조군 (즉시 등록, 영구 유지)

### `control_legacy_top10` — family: control
- **가설**: 현행 종합점수 상위 10 (기준선).
- **predicate**: `[{"col":"selected","op":"==","value":1}]`
- **의미**: 모든 신규 rule 이 이겨야 할 상대 기준. 점수 로직이 바뀌어도 selected 정의가
  따라가므로 자동 추적된다.

## F3 — NXT 괴리형 (1순위: 데이터 전부 사내 + 경쟁 적은 신시장)

### `f3_nxt_gap_quality`
- **매수자**: 본장 유동성 재진입자. 애프터마켓은 참여자가 적어 가격이 덜 효율적 —
  실수요가 만든 괴리는 익일 본장 유동성이 붙으며 재정렬된다.
- **predicate**: `nxt_gap_pct between [1.0, 6.0]` AND `nxt_listed == 1` AND
  `sector_rel_ret >= 0` (섹터 동조 = 착시 아님 방증) AND `change_pct between [0, 12]`
- **경계 논리**: 하한 1% 미만은 노이즈, 상한 6% 초과는 이미 다 먹힌 갭(다음 매수자 몫 없음).

### `f3_nxt_gap_thin` — **음의 가설 (착시 검증용)**
- **가설**: 섹터 동조 없는 단독 NXT 괴리(`nxt_gap_pct >= 3` AND `sector_rel_ret < 0`)는
  얇은 호가 착시라 익일 수익이 안 된다(기대: mean_net ≤ 0).
- **의미**: F3 본가설의 대우 검증. 이게 양(+)으로 나오면 F3 의 인과 논리 자체를 재검토.

## F1 — 뉴스 미반영형 (2순위: 라벨 인프라 기구축, 한계비용 ~0)

### `f1_fresh_news_unpriced`
- **매수자**: 장 마감 후/저녁 뉴스를 본 해석 매수자. 재료는 새로 등장했는데(14일 내 첫 언급)
  당일 가격 반응이 미미하면 반영 여지가 남는다.
- **predicate**: `news_first_today == 1` AND `news_unique_count >= 2` AND
  `change_pct between [0, 5]` (반응 부족) AND `news_pm_count >= 1` (신선도)
- **주의**: "시장이 보고 무시한 재료"일 가능성이 상존 — 그래서 검증 대상이다.

### `f1_news_surprise_burst`
- **가설**: 평소 조용하던 종목의 언급 폭증(서프라이즈)은 관심 유입의 선행 신호.
- **predicate**: `news_prior_avg <= 0.5` AND `news_unique_count >= 3` AND `change_pct between [2, 12]`

## F2 — 해외 동조 지연형 (3순위)

### `f2_us_semis_laggard`
- **매수자**: 아침 섹터 리밸런싱. 미국 반도체가 강한 밤, 국내 반도체 중 덜 오른 종목이
  아침에 따라간다.
- **predicate**: `market.sox_ret >= 1.5` AND `sector in ["반도체", "전기전자", "IT부품"]`(실제
  키움 업종명은 구현 시 확정) AND `sector_rel_ret <= 0` (아직 덜 반응)
- **참고**: futures_gate 의 섹터 민감도 통설을 검증하는 부수 효과도 있다(메모리: 미검증 가정).

## F4 — 후발 확산형 (4순위)

### `f4_sector_follower`
- **매수자**: 대장주를 놓친 추격 매수자 — 관심이 동섹터 후발주로 이동.
- **predicate**: `is_leader == 0` AND `sector_leader_chg >= 8` (대장 급등) AND
  `sector_rel_ret between [-3, 0]` (후발 저반응) AND `change_pct >= 0`

### `f4_theme_follower` (2026-07-05 추가 — 테마 단위 정밀판)
- **매수자**: 테마 대장이 부담스러운 추격 매수자 — 관심이 동일 테마 후발주로 확산.
- **predicate**: `theme_strength >= 3` (테마 당일 +3%↑) AND `change_pct between [0, 4]` (본인 저반응)

## F5 — 수급 구조형 (2026-07-05 추가 — 키움 장중 수급·차트 피처, 전부 선정 시점 컬럼)

### `f5_inst_frgn_dual_buy`
- **매수자**: 포지션을 하루에 다 못 채운 기관·외국인. 정보 우위 주체 둘이 같은 날 동반
  순매수하며 연속 수급까지 붙은 종목은 익일에도 이어 담는다(수급 연속성).
- **predicate**: `inst_net_buy > 0` AND `frgn_net_buy > 0` AND `supply_days >= 3` AND
  `change_pct between [0, 10]`

### `f5_retail_solo_pump` — **음의 가설 (착시 검증용)**
- **가설**: 기관·외국인이 순매도하는데 개인 매수만으로 오른 급등(`change_pct >= 5`)은
  받아줄 다음 매수자가 없어 익일 되돌림(기대: mean_net ≤ 0).
- **의미**: 검증되면 veto rule 전환 근거가 된다.
- **predicate**: `indv_net_buy > 0` AND `inst_net_buy < 0` AND `frgn_net_buy < 0` AND
  `change_pct >= 5`

### `f5_breakout_structure`
- **매수자**: 아침 신고가 돌파를 확인하고 진입하는 추세추종자. 52주 신고가 부근은 물린
  매물(저항)이 없어 정배열 돌파에 후속 자금이 붙는다.
- **predicate**: `ma_aligned == 1` AND `near_high == 1` AND `change_pct between [1, 8]`

### `f5_foreign_broker_top` (파생 컬럼 2차, 2026-07-05 등록)
- **매수자**: 창구를 통해 계속 사는 외국계 기관 — 상위 5 매수거래원 중 외국계 2곳 이상은
  기관성 자금 흔적이고, 포지션을 하루에 다 채우지 못한다.
- **predicate**: `foreign_brokers_buying == 1` AND `supply_score >= 50` AND `change_pct between [0, 12]`

### `f5_late_day_strength`
- **매수자**: 마감 강세를 확인하고 다음날 아침 따라붙는 모멘텀 매수자 — 오후장까지 매수
  우위가 유지되면 못 채운 수요가 익일 시초가로 이월된다.
- **predicate**: `afternoon_ret >= 1.5` (13시 시가 대비) AND `change_pct between [1, 12]`

### `f5_volume_surprise`
- **매수자**: 당일 소식을 저녁에 접하고 익일 아침 유입되는 후발 관심 매수자 — 평소 대비
  거래량 폭증은 신규 관심의 가장 원초적 신호.
- **predicate**: `vol_ratio >= 5` (20일 평균 대비) AND `change_pct between [2, 12]`

### `f5_prog_persistent` — f5_prog_negative_check 의 분리 가설
- **가설**: 하루치 프로그램 순매수는 역효과 의심이지만, 5일 중 4일 이상 연속 순매수는
  바스켓 리밸런싱성 지속 매수라 다르다.
- **predicate**: `prog_buy_days >= 4` AND `change_pct between [0, 10]`

### `f5_universe_new_entry`
- **매수자**: 새 주도주 후보를 다음날 발견하고 진입하는 후발 참여자 — 직전 14일 유니버스에
  없던 거래대금 상위 첫 등장은 시장 관심의 신규 발생(news_first_today 의 가격·수급 버전).
- **predicate**: `first_seen == 1` AND `change_pct between [3, 15]`

### `f5_frgn_exhaust_rise`
- **매수자**: 지분 확대 중인 외국인 — 소진율 실증가는 장중 잠정 순매수보다 확정적이고,
  지분을 늘리는 외국인은 며칠에 걸쳐 나눠 산다.
- **predicate**: `frgn_exhaust_chg >= 0.2` (%p, 직전 리포트 거래일 대비) AND `change_pct between [0, 10]`

## veto — 감액·제외 전용 (검증 없이 조기 live 가능, README §5-4)

### `veto_overheat_gap`
- **논리**: 당일 +15% 이상 과열 + NXT 애프터에서 추가 급등(`nxt_gap_pct >= 5`)은 내가 살
  시점엔 이미 남에게 넘길 구간 — 익일 시초가 고점 리스크. (기존 SCORE_OVERHEAT_PENALTY 의
  강화판이지만 감점이 아니라 명시적 제외라 귀속이 남는다.)
- **predicate**: `change_pct >= 15` AND `nxt_gap_pct >= 5`

### `veto_bad_news` (뉴스 악재 — 기존 로드맵 항목의 수용처)
- **predicate**: `news_sentiment <= 30` AND `news_unique_count >= 2`
- **참고**: news_sentiment 는 top-10 후보만 LLM 라벨이 붙으므로 커버리지 한계 명시.
  veto 는 reduce-only 라 결측 시 미적용이 안전 기본값.

## exit_label 변주 (청산창 가설 — Phase 2 라벨 축적 후 등록)

같은 predicate 에 `exit_label` 만 바꾼 쌍둥이 rule 로 청산창을 실측 비교한다.
예: `f3_nxt_gap_quality` (exit=next_open_ret) vs `f3_nxt_gap_quality__nxt_exit`
(exit=nxt_open_ret). **rule 폭발 방지**: 쌍둥이는 live 승격된 rule 에만 만든다.

## 등록 방법

Phase 3 의 `POST /api/edge-rules` 로 등록하거나 시드 스크립트
(`jongalab/sql/8. seed_edge_rules.sql` 또는 단발 스크립트)로 일괄 삽입.
등록일(registered_at)이 승격 판정의 표본 시작일이 되므로 **Phase 1·2 배포 직후 바로 등록**한다.
