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

### `f3_nxt_gap_thin` — **음의 가설 (착시 검증용, role=veto)**
- **가설**: 섹터 동조 없는 단독 NXT 괴리(`nxt_gap_pct >= 3` AND `sector_rel_ret < 0`)는
  얇은 호가 착시라 익일 수익이 안 된다(기대: mean_net ≤ 0).
- **의미**: F3 본가설의 대우 검증. 이게 양(+)으로 나오면 F3 의 인과 논리 자체를 재검토.
- **role**: 2026-07-29 `selector` → **`veto`** 재분류(sql/42) — 아래 `f5_retail_solo_pump`
  와 같은 이유(음의 가설을 selector 로 두면 게이트 부호가 반대로 붙는다).

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

### `f5_retail_solo_pump` — **음의 가설 (착시 검증용, role=veto)**
- **가설**: 기관·외국인이 순매도하는데 개인 매수만으로 오른 급등(`change_pct >= 5`)은
  받아줄 다음 매수자가 없어 익일 되돌림(기대: mean_net ≤ 0).
- **의미**: 검증되면 veto rule 전환 근거가 된다.
- **role**: 2026-07-29 `selector` → **`veto`** 재분류(sql/42). 7/7 시드는 짝 가설
  (`f5_inst_frgn_dual_buy`)과 같은 자로 재려고 음의 가설을 매수 축에 뒀는데, 그러면
  **게이트 부호가 반대로 붙는다** — 가설대로 손실이면 게이트는 침묵(veto 전환 근거가 쌓여도
  알림 없음)이고, 가설과 반대로 이익이면 🟢'승격 후보'로 실탄 매수 후보가 된다. 실제로
  2026-07-29 그 상태가 됐다(n=12·10거래일, mean_net +1.90%, 일 t=1.18 — 평균의 전부가
  7/15 HLB·7/28 코스모로보틱스 이틀에서 나오고 그 이틀을 빼면 초과 −0.31%).
  7/19 배치의 음의 가설은 처음부터 veto 로 등록됐다(`veto_prior_high_wall` 등) — 이건 잔재였다.
- **재분류 후 판정**: veto 실익 게이트(제외 종목 mean_net<0)에서 +1.90% 로 정상 탈락.
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

### `f5_ma5_reclaim` (2026-07-19 추가 — 사용자 제안 가설, sql/21)
- **매수자**: 눌림목 반등 확인 매수자 — 단기 조정(전일 종가가 5일선 아래) 뒤 강한 양봉으로
  5일선을 재탈환하면 조정 종료 신호로 읽는 눌림목·추세추종 자금이 익일 아침 진입한다.
- **predicate**: `ma5_reclaim == 1` (①전일 종가<전일 MA5 ②당일 양봉 ③현재가>당일 MA5)
  AND `change_pct between [3, 15]` ('강한'은 밴드로 분리해 임계 명시)
- **정정 이력**: 최초안의 '전일 음봉' 조건은 등록 당일(표본 0 시점) 사용자 정정으로 제거 —
  이탈 '봉 색'이 아니라 이탈 '위치'가 가설의 본질. 사전 등록 원칙 위반 아님(축적 전 정정).
- **사전 점검(참고용, 승격 근거 아님)**: 6/26~7/15 유니버스 재현 — 매칭 n=33/7거래일
  (일 1~11건, 빈도 충분), next_open_ret −0.44%·승률 45.5% vs 나머지 +0.25%·52.2% —
  **인샘플 무엣지**(음의 방향이나 유의성 없음, 반증 아님). out-of-sample 이 판정한다.

## veto — 감액·제외 전용 (검증 없이 조기 live 가능, README §5-4)

### `veto_overheat_gap`
- **논리**: 당일 +15% 이상 과열 + NXT 애프터에서 추가 급등(`nxt_gap_pct >= 5`)은 내가 살
  시점엔 이미 남에게 넘길 구간 — 익일 시초가 고점 리스크. (기존 SCORE_OVERHEAT_PENALTY 의
  강화판이지만 감점이 아니라 명시적 제외라 귀속이 남는다.)
- **predicate**: `change_pct >= 15` AND `nxt_gap_pct >= 5`

### `veto_prior_high_wall` (2026-07-19 추가 — 차트 레벨 피처 1차, sql/20)
- **논리(음의 가설)**: 당일 +3% 이상 급등으로 250일 전고점 직하단(`dist_prior_high_pct`
  -5%~-1%)에 도달했지만 못 뚫은 종목은, 전고점에 물린 보유자들의 본전 매도가 익일 시가부터
  출회되어 갭 상승을 누른다. `f5_breakout_structure`(돌파 지속, 양의 가설)와 경합 —
  두 페이퍼 성적이 "전고점 근처"의 손익 분기(벽 vs 돌파)를 실측으로 가른다.
- **predicate**: `dist_prior_high_pct between [-5, -1]` AND `change_pct >= 3`
- **피처 주의**: 전고점은 **당일 봉 제외** 고가 기준 — 포함하면 급등주는 항상 자기 자신이
  전고점이 되어 매물벽 정보가 사라진다.

### `veto_round_figure_cap` (2026-07-19 추가 — 차트 레벨 피처 1차, sql/20)
- **논리(음의 가설)**: 라운드피겨(1·2·5×10^k원) 직하단 2% 이내 마감은 해당 레벨에 걸린
  심리적 지정가 매도 물량이 익일 시가 상단을 캡한다. 효과 크기가 작을 수 있어 표본으로 실측.
- **predicate**: `round_dist_pct between [-2, 0]`
- **비고**: 전저점/지지 피처는 만들지 않는다 — 유니버스(당일 거래대금 상위·급등 중심)에
  전저점 부근 종목이 사실상 없어 매칭 0 으로 표본이 쌓이지 않는다(2026-07-19 점검).

### `f5_prior_high_break` · `f5_round_figure_break` (2026-07-19 추가 — sql/22, 돌파 대칭 쌍)
- **매수자**: 돌파 확인 추세추종자 — 전고점/라운드피겨를 실제로 넘어선 종목은 머리 위
  매물·매도벽이 소화된 상태라 아침 후속 자금이 붙는다는 양의 가설.
- **predicate**: `dist_prior_high_pct between [0, 5]` AND `change_pct >= 3` /
  `round_dist_pct between [0.1, 2]` AND `change_pct >= 0`
- **의미**: sql/20 매물벽 음의 가설(직하단)과 같은 축의 대칭 쌍 — 손익 분기(벽 vs 돌파)를
  데이터로 가른다. `f5_breakout_structure`(정배열+52주 **종가**고점 95% '근처')와 달리
  고가 기준 **실제 돌파**만 잡는다.
- **사전 점검(참고용)**: 6/26~7/15 인샘플 재현 — 전고점 돌파 n=9 **−2.64%**(t=−2.1, 역방향),
  매물벽 veto 밴드는 n=4 **+1.70%**(이것도 역방향), 라운드 돌파 n=6 −0.55%(무엣지).
  전부 표본 극소 — 방향이 뒤집혀 있다는 것 자체가 대칭 측정이 필요한 이유. 음(−) 확정 시
  selector 승격 대신 veto 재등록 후보.

### `f5_frgn_surge_pullback1` · `f5_frgn_surge_pullback2` · `f5_frgn_surge_carry` (2026-07-19 — sql/23·24, 외인 서지 축)
- **출처**: 종가베팅 팁 PDF(트레이더 칼럼) 통설 "외인 대량 유입 후 수급 1음봉/2음봉에서 종가
  분할 매수" — 눌림(통설)과 지속(대칭)을 한 축으로 등록해 데이터가 가른다.
- **정정 이력**: sql/23 은 눌림을 통합 1건(benchmark)으로 등록했으나 등록 당일(표본 0)
  사용자 정정으로 1음봉/2음봉 분리 + selector 전환 재등록(sql/24, ma5_reclaim 전례).
- **피처**: `days_since_frgn_surge`(직전 거래일 중 외인 순매수 ≥100억 서지의 경과 거래일,
  1=어제·최대 4, **당일 서지 제외** — 당일 유입은 `frgn_net_buy` 가 이미 본다) ·
  `red_candle`(당일 음봉=현재가<당일 시가 — 음전과 다른 정보, 갭업 후 밀림 포착) ·
  `red_candle_streak`(당일 포함 연속 음봉 수, 당일 양봉=0 — 2음봉 판정용).
  추가 API 콜 0 — supply_history(ka10059)·일봉(ka10081) 기수집 응답 파생.
- **predicate**:
  1음봉 `days_since_frgn_surge == 1` AND `red_candle == 1` /
  2음봉 `days_since_frgn_surge == 2` AND `red_candle_streak >= 2`(연속 음봉만) /
  지속 `days_since_frgn_surge between [1,2]` AND `red_candle == 0` AND `change_pct >= 0`
- **role**: 전부 selector candidate. 단 음봉 매칭 표본 대부분이 음전이라 live 승격돼도
  실효 집행은 음봉+양전(갭업 후 밀림) 부분집합에 한정된다(선정 레이어가 음전 후보를
  핸드오프에서 제외) — 승격 판단 시 감안. 음(−) 확정 시 veto 재등록 후보.
- **사전 점검(2026-07-19, 6/26~7/18 인샘플 재현, 참고용)**: 기준선 +0.18%(n=345).
  1음봉 n=55 **+0.22%**(승률 52.7%, 기준선 수준) / 2음봉(연속) n=8 **+0.50%**(표본 극소 —
  전일 유니버스 커버리지 한계, 라이브 피처는 일봉 기반이라 무관) /
  지속 n=61 **+1.47%**(승률 67.2%, t=2.03). out-of-sample 이 판정.
- **관찰 메모**: 서지 D-2 + 당일 음봉인데 전일 양봉(쉬었다 반락)은 n=22 **−1.16%**(승률
  22.7%, t=−1.99) — 눌림이 아니라 반락 시작일 가능성, 표본 쌓이면 veto 후보로 별도 등록 검토.
  기관 동반 조건(PDF의 "기관 연속성")은 인샘플 개선 효과가 없어 등록하지 않았다.

### `f5_prog_pm_reversal` (2026-07-19 추가 — sql/26, 프로그램 오후 전환)
- **출처**: 매물대/종가베팅 PDF(트레이더 칼럼) 공통 통설 — "오전 프로그램 매도 출회 →
  오후 프로그램 매수 전환"을 종가매매 진입 신호로 선호(레인보우로보틱스 사례).
  일별 prog_net_buy 가점은 실측 역효과(2026-07-03)로 제거됐으나 그건 하루 합계 —
  이 rule 은 **일중 방향 전환**이라 별개 축.
- **피처**: `prog_am_net`(정오 창 실행 시점 프로그램 누적 순매수) ·
  `prog_pm_net`(오후 실행 누적 − 정오 누적). ka90008 틱 시계열은 유동 종목에서 12:00
  도달에 50페이지+ 가 필요해(실측: 삼성전자 12:00~14:30 구간만 11,256틱) 틱 워킹을
  기각하고, 30분 주기 closing_bet 재실행의 **2점 스냅샷 차분**(후보당 1페이지)으로 캡처.
  수집 창 12:00~15:35 제한 + tm 가드(키움이 당일 데이터 없으면 최근 거래일 폴백 반환 —
  개장 전 실행의 전일 오염 방지) + repository 보존 upsert(am=first-write-wins, pm=NULL 무시).
- **predicate**: `prog_am_net <= 0` AND `prog_pm_net > 0` AND `change_pct >= 0`
- **사전 점검 불가**: 틱/스냅샷 이력이 없어 인샘플 재현 불가 — 초기 시드(sql/8)와 같은
  순수 out-of-sample 검증. 첫 캡처는 등록 다음 거래일부터.

### `f5_bottom_entry_dual_buy` · `f5_frgn_surge_flat34` · `f5_supply_turn_vol2` (2026-07-19 — sql/27~29, 수급매매 용어 3종)
> 2026-08-10 은어 제거로 title(sql/62)·슬러그(sql/63)가 모두 바뀌었다 — predicate·표본은 그대로.
> 등록 당시 슬러그는 각각 `f5_supply_missile`·`f5_supply_eagle`·`f5_supply_inflection`(구 제목: 수급 미사일·독수리·변곡점).
- **출처**: 수급매매 용어 PDF(트레이더 칼럼) — 신규 피처 없이 **기존 컬럼 조합만**으로 등록
  (같은 PDF의 수급 1,2음봉·돌파매매는 기등록, N자형·뒷발차기는 새 피처 필요라 보류).
- **바닥권 첫 등장 + 외인·기관 동반 매수**(`f5_bottom_entry_dual_buy`): 소외 중소형주 바닥권의 외인·기관 동반 매수 첫 등장.
  `first_seen==1` AND `inst_net_buy>0` AND `frgn_net_buy>0` AND `market_cap<=2조` AND
  `dist_prior_high_pct<=-30`. 사전 점검 n=1(+0.29%) — **저빈도**(전제 충족 자체가 16거래일
  2~3건), 모집단 first_seen 전체는 −1.62%·승률 35%라 그 반례 부분집합 가설.
- **외인 대량 매수 후 3~4일 횡보**(`f5_frgn_surge_flat34`): 서지 3~4일 뒤 횡보(2차 상승 직전 매집). `days_since_frgn_surge between
  [3,4]` AND `change_pct between [-3,3]` — 서지 축(1~2일 눌림/지속)의 확장으로 경과 축 완성.
  사전 점검 n=16/8일 **+1.55%** 승률 62.5% t=1.79 — 인샘플 양(+).
- **순매수 전환 첫날 + 거래량 2배**(`f5_supply_turn_vol2`): 연속 순매수 첫날(전환) + 거래량 2배 + 양전. `supply_days==1` AND
  `vol_ratio>=2` AND `change_pct>=0`. vol_ratio>=3 은 매칭 0이라 등록 전 완화.
  사전 점검 n=5(+1.92%, 극소) — 거래량 무관 전체는 −0.65%라 거래량 필터가 핵심 변별.

### 매물대 프로파일 피처 (2026-07-19, sql/25 — **rule 없음**, 선축적만)
- `overhead_vol_ratio`(250일 거래량 중 현재가 위 비중 — 일봉 고저 균등 배분 근사) ·
  `poc_dist_pct`(최대 거래 집중가 POC 거리 %). 레벨 축(전고점·라운드피겨)의 '위치'에
  '두터움(거래량 가중)'을 보태는 피처.
- rule 을 등록하지 않은 이유: 같은 레벨 저항 축의 rule 이 이미 5종 미검증 대기 중 —
  8월 판정 후 결과에 '두터움' 조건부 결합(예: 벽이 두터울 때만 veto)으로 등록한다.
  표본 축적은 달력 시간이 자산이라 컬럼은 지금부터 굽는다.

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
