// 콘텐츠에서 언급된 종목별 판단 (구조화 요약)
export interface StockCall {
  name: string;
  ticker?: string | null;
  stance?: '호재' | '악재' | '중립' | string;
  conviction?: '상' | '중' | '하' | string;
  horizon?: '단기' | '중기' | '장기' | string;
  reason?: string;
}

export interface ContentAnalysis {
  id: number;
  external_id: string;
  source_name: string;
  title: string;
  analysis_content: string;
  sentiment_score?: number;
  platform: 'youtube' | 'telegram' | 'news';
  source_url?: string;
  created_at: string;
  related_tickers?: { ticker: string; name: string }[];
  tldr?: string;               // 한 줄 대표 요약
  tags?: string[];             // 테마 해시태그
  stock_calls?: StockCall[];   // 종목별 방향·확신·시간축
}

// 아카이브 캘린더용 일자별 1등 종목 (/api/stock-report/top-picks)
export interface TopPick {
  stock_code: string;
  stock_name: string;
  score: number;
}

// GET /api/stock-report/record-summary — 최근 N 거래일 선정 종목 누적 성적.
// 모집단은 selected=1 + 갭 체크 완료 행(rank_no 로 자르지 않는다).
export interface RecordDay {
  date: string;
  pct: number;
}

export interface RecordSummary {
  days: number;              // 집계된 거래일 수
  from_date: string | null;
  to_date: string | null;
  picks: number;             // 총 종목 수(= wins+losses+flats)
  wins: number;
  losses: number;
  flats: number;
  win_rate: number;          // %
  avg_gap_pct: number;       // 익일 시가 갭 평균 등락률 %
  // ⚠️ 실체결 손익률은 매매 경로 가동 이후 구간에만 있어 **갭과 창이 다르다**.
  // 두 평균을 나란히 놓으면 "실체결이 더 좋다"로 오독되므로, 화면은 창이 다를 때
  // exec_from_date~exec_to_date 를 반드시 함께 표기한다.
  avg_exec_ret: number | null;
  exec_samples: number;
  exec_days: number;
  exec_from_date: string | null;
  exec_to_date: string | null;
  best_day: RecordDay | null;
  worst_day: RecordDay | null;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  pagination: {
    current_page: number;
    limit: number;
    total_items: number;
    total_pages: number;
    has_next_page: boolean;
    has_prev_page: boolean;
  } | null;
}

export interface MarketIndex {
  symbol: string;
  name: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  sparkline?: number[] | null;
  // 미국 정규장 밖 시세 (SKHY·EWY·KORU 등 장 밖 거래가 있는 심볼만).
  // extended_percent 는 정규장 종가 대비 등락률. 정규장 중에는 값이 없다.
  extended_price?: number | null;
  extended_percent?: number | null;
  market_state?: string | null;
}

export interface MarketIndices {
  US: MarketIndex[];
  KR: MarketIndex[];
  COMMODITIES: MarketIndex[];
  FUTURES: MarketIndex[];
}

export interface MarketIndexHistory {
  symbol: string;
  name: string;
  candles: HourlyCandleItem[];
}

export interface Source {
  id: number;
  platform: string;
  identifier: string;
  name: string | null;
  is_active: boolean;
  created_at?: string;
}

export interface TelegramUser {
  id: string;
  name: string;
  role: 'ADMIN' | 'NORMAL';
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface TickerDictionary {
  id: number;
  company_name: string;
  ticker_symbol: string;
  status: 'PENDING' | 'ACTIVE' | 'INACTIVE';
  sector?: string | null;
  sector_updated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SupplyHistoryItem {
  date: string;
  inst_net_buy: number;
  frgn_net_buy: number;
  indv_net_buy: number;
  prog_net_buy: number;
}

export interface HourlyCandleItem {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  extended?: boolean; // 정규장 밖(프리/애프터마켓) 분봉 — 시장 상세 차트에서 흐리게 표시
}

export interface StockReport {
  id: number;
  report_date: string;
  stock_code: string;
  stock_name: string;
  sector: string | null;
  current_price: number;
  change_pct: number;
  trading_value: number;
  market_cap: number;
  supply_grade: 'S' | 'A' | 'B' | 'C' | 'D';
  supply_score: number;  // 최근 5일 수급 정밀 점수 (0~100)
  inst_net_buy: number;
  frgn_net_buy: number;
  indv_net_buy: number;
  prog_net_buy: number;
  supply_days: number;
  supply_history: SupplyHistoryItem[];
  ma_aligned: boolean;
  near_high: boolean;
  hourly_candles: HourlyCandleItem[];
  is_leader: boolean;
  is_theme_stock: boolean;
  content_score: number;
  news_count: number;               // 당일 뉴스 언급 건수 (재료 신호)
  news_unique_count?: number;       // 당일 고유 기사 수 (헤드라인 dedup, 연구 라벨)
  news_pm_count?: number;           // 12시 이후 언급 수 (신선도, 연구 라벨)
  news_first_today?: boolean;       // 직전 14일 내 첫 언급 여부 (연구 라벨)
  news_prior_avg?: number | null;   // 직전 7일 일평균 언급 수 (서프라이즈 분모)
  news_summary?: string | null;     // 배치 LLM 재료 요약 (후보 소수만)
  news_sentiment?: number | null;   // LLM 재료 방향 0~100 (요약 후보만)
  news_catalyst?: string | null;    // LLM 재료 유형 (실적/수주계약/임상승인/M&A/정책테마/증자감자/지분변동/기타)
  // 재료 지속성 라벨 (sql/40, 축·합성 v2 = sql/52) — ⚠️ candidate rule 표본(관찰 전용, 미검증).
  // 화면에서 매수 신호처럼 보이면 안 된다(색을 손익 방향으로 쓰지 말 것 — MaterialBadge 참조).
  news_next_milestone?: boolean | null; // 재료에 남은 다음 예정 사건이 있는가
  news_milestone_horizon?: string | null; // 그 사건 시점: 1주내 / 1개월내 / 그이후 / 불명 (v2 등급 결정축)
  news_amount_locked?: boolean | null;  // 수치가 이미 확정·소진됐는가 (v2 에서 등급 결정에는 미사용)
  news_material_size_ratio?: number | null; // 재료 금액 ÷ 시가총액 (0.035 = 시총의 3.5%)
  news_driver_scope?: string | null;    // 종목단독 / 산업사이클 / 불명
  news_stage?: string | null;           // 첫발표 / 진행 / 마무리 / 불명
  news_durability?: NewsDurability;     // 파생 등급 (연속/중립/소진), NULL=미판정
  news_durability_v?: number | null;    // 합성 규칙 버전(2=현행). v1 라벨은 뜻이 달라 섞어 읽지 말 것
  news_label_reason?: string | null;    // 판정 근거 한 문장 (육안 감사용)
  news_followup_days?: number | null;   // 채점: +1~+10일 중 시세보도 제외 언급 있던 날짜 수
  news_headlines?: string[];        // 최근 헤드라인 목록
  score: number;
  reason: string;  // 종합 점수 구성요소로 자동 생성된 매수 이유
  rank_no: number;
  // 선정 근거 (sql/43) — hybrid/rules 모드에서 이 종목을 뽑은 live 룰 name 콤마 목록.
  // ⚠️ 값이 있으면 **점수 순위와 무관하게** 룰이 뽑은 종목이다(점수 62위가 목록에 들 수 있다).
  // null = 점수순 선정. 화면은 이 구분을 반드시 드러낸다(StockReportCard 참조).
  rule_names?: string | null;
  gap_nxt_price?: number | null;
  gap_nxt_pct?: number | null;
  gap_krx_price?: number | null;
  gap_krx_pct?: number | null;
  gap_checked_at?: string | null;
  // 무상증자 권리락 배정비율(sql/50). 값이 있으면 gap_*_pct 는 **권리락 조정 기준가 대비**다
  // (조정 기준가 = 리포트가 / (1 + 비율)) — 화면은 조정 기준가와 배지를 함께 보여준다.
  gap_ex_rights_ratio?: number | null;
  exec_leg_ret?: number | null;
  exec_leg_venue?: 'NXT' | 'KRX' | null;
  created_at?: string;
}

export interface ContentAnalysisItem {
  id: number;
  title: string;
  analysis_content: string;
  sentiment_score: number;
  source_name: string;
  platform: string;
  source_url?: string;
  created_at?: string;
}

// 재료 지속성 등급 — null/undefined = 미판정(억지로 채우지 않는다)
export type NewsDurability = '연속' | '중립' | '소진' | null;

// /api/news/heat — 정렬은 건수가 아니라 자기 기저 대비 배수(surprise).
// 건수 정렬은 시총 랭킹이 되어 대형주가 상단에 고정된다.
export interface NewsHeatItem {
  ticker: string;
  company_name: string | null;
  mention_count: number;
  last_at: string | null;
  prior_avg?: number;          // 직전 7일 일평균 언급 수 (배수의 분모, 하한 1)
  surprise?: number;           // mention_count / max(prior_avg, 1)
  durability?: NewsDurability; // 오늘 유니버스 종목만 (밖이면 null)
  catalyst?: string | null;
  summary?: string | null;
  in_universe?: number;        // 1 = 오늘 유니버스에 든 종목
}

// /api/news/materials — 그 날 뉴스가 있던 유니버스 종목의 재료 라벨 슬림 행
export interface NewsMaterialRow {
  stock_code: string;
  stock_name: string;
  sector: string | null;
  change_pct: number | null;
  market_cap?: number | null;
  trading_value?: number | null;
  score?: number | null;
  rank_no: number;
  selected: number;
  news_count: number;
  news_unique_count?: number | null;
  news_pm_count?: number | null;
  news_first_today?: boolean | null;
  news_prior_avg?: number | null;
  news_summary?: string | null;
  news_sentiment?: number | null;
  news_catalyst?: string | null;
  news_next_milestone?: boolean | null;
  news_milestone_horizon?: string | null;   // v2 등급 결정축 (1주내/1개월내/그이후/불명)
  news_amount_locked?: boolean | null;
  news_material_size_ratio?: number | null; // 재료 금액 ÷ 시가총액
  news_driver_scope?: string | null;
  news_stage?: string | null;
  news_durability?: NewsDurability;
  news_label_reason?: string | null;
  news_followup_days?: number | null;
}

// 종목별 당일 뉴스 헤드라인 (/api/news/{ticker}, news_mention 원천)
export interface NewsMentionItem {
  headline: string;
  source_url: string | null;
  channel_name: string | null;
  created_at: string | null;
  is_price_report?: boolean;   // 재료가 아니라 그날 시세를 옮긴 기사 (화면에서 접는다)
}

// /api/news/stream — 뉴스 탭 헤드라인 스트림. news_mention 은 '헤드라인 × 종목' 1행이라
// 백엔드가 source_url 로 접어 **기사 1건 + 종목 칩 N개** 로 돌려준다.
export interface NewsStreamStock {
  ticker: string;
  name: string;
}

export interface NewsStreamItem {
  headline: string;
  source_url: string | null;
  channel_name: string | null;
  created_at: string | null;
  stocks: NewsStreamStock[];
  is_price_report?: boolean;
}

export interface NewsStreamResponse {
  success: boolean;
  data: NewsStreamItem[];
  // ⚠️ 지금 조건(hide_price·q·ticker)으로 **나열되는** 기사 수다. '그 날 전체'가 아니다 —
  // 화면 헤더·'더 보기' 카운터·실제 표시 건수를 한 수로 맞추려고 서버가 거르고 센다.
  total: number;
  price_total?: number; // 숨긴 시세 기사 수 (토글 라벨용)
  has_more: boolean;
}

// 종합점수 구성 — 서버(`core/backtest.score_breakdown`)가 **현재 가중치**로 낸 항목별 100점 환산 점수.
// ⚠️ 프론트가 가중치를 따로 갖지 않는다. 가중치는 주간 튜닝(`strategy_config`)으로 바뀌므로
// 화면이 미러를 들면 조용히 어긋난다(경위: docs/history/frontend-ui.md).
// 튜닝 이후에 조회한 과거 리포트는 `total` 이 저장된 `score` 와 다를 수 있어, 화면이 그 차이를 밝힌다.
export interface ScoreBreakdownItem {
  key: string;
  label: string;
  points: number;      // 획득 점수 (100점 환산)
  max_points: number;  // 만점 (100점 환산)
}

export interface ScoreBreakdownPenalty {
  key: string;
  label: string;
  points: number;      // 감점이라 음수
}

export interface ScoreBreakdown {
  items: ScoreBreakdownItem[];
  penalty?: ScoreBreakdownPenalty | null;
  total: number;
}

export interface StockReportDetail {
  report: StockReport;
  content_analyses?: ContentAnalysisItem[];
  score_breakdown?: ScoreBreakdown | null;
}

export interface SectorStock {
  stk_cd: string;
  stk_nm: string;
  cur_prc: string;
  flu_rt: string;
}

export interface SectorReport {
  id: number;
  report_date: string;
  thema_grp_cd: string;
  thema_nm: string;
  stk_num: number;
  flu_rt: number;
  dt_prft_rt: number;
  main_stk: string | null;
  rising_stk_num: number;
  fall_stk_num: number;
  rank_no: number;
  stocks: SectorStock[];
  created_at?: string;
}

export interface MentionTicker {
  ticker: string;
  name: string;
  mention_count: number;
  avg_sentiment: number | null;
}

export interface MentionSector {
  sector: string;
  mention_count: number;
  tickers: MentionTicker[];
}

export interface MentionStats {
  window_hours: number;
  total_contents: number;
  total_mentions: number;
  dropped_unmapped_count: number;
  sectors: MentionSector[];
}
export type WeightMap = Record<string, number>;

export interface WeightTuningSample {
  stk_cd: string;
  name: string;
  trade_date: string;
  realized_pnl: number;
  outcome: 'WIN' | 'LOSS' | 'FLAT';
  score: number;
  supply_score: number;
  ma_aligned: boolean;
  near_high: boolean;
  trading_value: number;
  is_leader: boolean;
  is_theme_stock: boolean;
  supply_days: number;
  content_score: number;
  change_pct: number;
}

export interface WeightBacktestMetrics {
  winner_avg_score: number | null;
  loser_avg_score: number | null;
  spread: number | null;
  pnl_rank_corr: number | null;
  scores: { stk_cd: string; name: string; outcome: string; realized_pnl: number; score: number }[];
}

export interface WeightBacktest {
  sample_count: number;
  current: WeightBacktestMetrics;
  proposed: WeightBacktestMetrics;
  spread_delta: number | null;
  corr_delta: number | null;
  verdict: 'IMPROVES' | 'WORSENS' | 'NEUTRAL' | 'INSUFFICIENT';
  note: string;
}

export interface WeightTuningProposal {
  id: number;
  week_start: string;
  week_end: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'archived';
  sample_count: number;
  winners_count: number;
  losers_count: number;
  total_realized_pnl: number;
  current_weights: WeightMap;
  proposed_weights: WeightMap;
  rationale: string | null;
  dataset: WeightTuningSample[] | null;
  backtest?: WeightBacktest | null;
  created_at: string;
  applied_at: string | null;
}

// ── Edge Ledger (가설 스코어보드) — 백엔드 edge_rule / edge_rule_daily 응답 shape 과 1:1 ──
export interface EdgeRuleStats {
  n: number;
  n_days?: number;              // 라벨 표본이 있는 거래일 수 — 승격 게이트(PROMO_MIN_DAYS)
  mean_net: number | null;      // 비용(EDGE_COST_PCT) 차감 후 평균 순수익(%)
  win_rate: number | null;
  std: number | null;
  ci_low: number | null;        // 단측 95% 신뢰구간 하한 — 승격 게이트(>0, strict 정책)
  mean_net_days?: number | null; // 일 등가중 평균(%) — 매칭 많은 날 쏠림을 드러냄
  t_days?: number | null;        // 일 클러스터 t — 승격 게이트(>=거래일 자유도 t 임계값)
  // ── 유니버스 자기제외 초과 계열 — **게이트 미사용, 룰 상세 화면 표기 전용** ──
  // "평균보다 수익이 크지 않더라도 안정적으로 수익이 나면 그만"이라 판정에서 빼고 참고값으로만 둔다.
  n_exc?: number;                // 초과 표본 수(기준선을 구할 수 있었던 종목-일)
  mean_exc?: number | null;      // 그날 유니버스(자기 제외) 대비 초과수익(%)
  ci_low_exc?: number | null;    // 초과 기준 CI 하한
  mean_exc_days?: number | null; // 초과 일 등가중 평균(%)
  t_days_exc?: number | null;    // 초과 일 클러스터 t
  // ── 시장 회귀 계열 — 초과 계열이 beta=1 을 강제해 저beta 방어형 룰을 상승장에서 죽이는
  // 문제를 푼다. **recent_alpha 만 강등 게이트가 쓰고**(core/edge_policy.check_demotion)
  // 나머지는 화면·수동 검토용 진단값이다.
  beta?: number | null;          // 시장 민감도 — 룰수익 = alpha + beta x 시장
  alpha?: number | null;         // 시장 몫을 beta 만큼 뺀 잔차(%, 누적 표본)
  t_alpha?: number | null;       // alpha 의 t
  recent_alpha?: number | null;  // 최근 창 alpha — 강등 게이트(selector <0 / veto >0)
  down_day_n?: number;           // 시장이 내린 날의 거래일 수
  down_day_mean?: number | null; // 그 날들의 평균 순수익(%) — "하락장에도 버티는가"
  worst_low_ret: number | null; // 매칭 종목 익일 저가 최악값(꼬리)
  updated_through: string | null;
  recent_n?: number;            // 강등 감시 최근 창(최근 10거래일) 표본 수
  recent_n_days?: number;       // 강등 감시 최근 창의 거래일 수
  recent_mean_net?: number | null;
  recent_mean_net_days?: number | null; // 최근 창 일 등가중(진단값)
  // 승격 게이트(core/edge_policy.check_promotion) 통과 여부 — 평가기가 계산해 저장.
  // 프론트는 이 값을 렌더링만 한다(조건을 프론트에서 재계산하지 않음 — 단일 소스).
  promo_eligible?: boolean;
  // 게이트를 막고 있는 항목의 짧은 라벨 + 적용 중인 정책. 프론트가 min_sample 등으로 조건을
  // 재추정하다 게이트 변경과 어긋나는 것을 막기 위해 서버가 직접 내려준다.
  promo_blockers?: string[];
  promo_policy?: 'strict' | 'experimental';
  decision_stage?: 'discovery' | 'confirming' | 'decided';
}

export interface PredicateCond {
  col: string;
  op: string;
  value?: unknown;
}

// 판정 기록(sql/39) — 매일 재평가로 오탐이 불어나는 것을 막으려 판정을 사전 시점 1회로 묶은 결과.
// 발견(누적 거래일 1~10) → 확인창(11~20, 발견에 쓰지 않은 새 표본) → 종결.
export interface EdgeRuleDecisionStep {
  at: string;
  n_days: number | null;
  pass: boolean;
  // 판정에 쓴 값 — selector 는 mean_net>0, veto 는 mean_net<0(자는 같고 부호만 반대).
  mean_net?: number | null;
  t_days?: number | null;
  // 아래 초과 계열은 참고 기록(판정 무관).
  mean_exc: number | null;
  t_days_exc?: number | null;
  reasons: string[];
  exec_blocked?: string[] | null;  // 선정 시점 실행 불가 — 통계 탈락과 구분(설계 변경 시 재검토)
}

export interface EdgeRuleDecision {
  discovery?: EdgeRuleDecisionStep;
  confirm?: EdgeRuleDecisionStep;
  decided_at?: string;
  // exec_blocked: 통계와 무관하게 **매수 시점에 평가할 방법이 없어** 종료(2026-08-13, sql/64).
  // 다른 verdict 는 rule_evaluator 가 통계로 찍지만 이것만 수동 종료라 retire_reason 이 함께 온다.
  verdict?: 'confirmed' | 'discovery_failed' | 'confirm_failed' | 'exec_blocked';
  retire_reason?: string;   // 종료 사유(사람이 읽는 문장) — 화면은 이 값을 그대로 보여준다
}

export interface EdgeRule {
  id: number;
  name: string;
  title: string | null;        // 카드 제목(한글) — NULL 이면 name 슬러그 폴백
  family: string;              // 도메인: f1_news / f2_global / f3_nxt / f4_laggard / f5_supply / f6_ah / f8_value / control
  role: 'selector' | 'veto' | 'benchmark';  // 역할: 선정 / 위험 회피(제외 전용) / 측정·기준선
  description: string;
  predicate: PredicateCond[];
  exit_label: string;
  // 두 축이 한 컬럼에 들어 있다 — 원장(candidate/live/retired, 사람 결정)과
  // 운용(live↔paused, rule_evaluator 자동). paused 는 선정에서 표만 빠지고 채점은 계속된다.
  status: 'candidate' | 'live' | 'paused' | 'retired';
  min_sample: number;          // 참고값 — 2026-07-28 승격 게이트에서 제외(단위가 거래일 규율과 어긋남)
  registered_at: string;
  stats: EdgeRuleStats | null;
  decision: EdgeRuleDecision | null;  // 판정 기록(sql/39) — 재시험 금지용 영구 기록
  created_at: string;
  promoted_at: string | null;
  retired_at: string | null;
  paused_at: string | null;    // 마지막 live↔paused 전이 시각
}

export interface EdgeRuleMatched {
  code: string;
  name: string;
  ret: number | null;   // exit_label 값(비용 미차감 원본)
  low: number | null;   // next_low_ret(꼬리)
  change_pct?: number | null;  // 당일 등락률 — matched 이력 API 만 조인 제공
  selected?: number | null;    // 현행 점수 톱10 선정 여부(1/0) — matched 이력 API 만 조인 제공
}

// GET /api/edge-rules/{id}/matched — 날짜별 매칭 기록(매칭 있던 날만, 최신→과거)
export interface EdgeRuleMatchedDay {
  report_date: string;
  n_matched: number;
  mean_net_ret: number | null;  // 비용 차감 후 평균(개별 ret 는 원본)
  matched: EdgeRuleMatched[];
}

// daily 시계열은 matched(일별 매칭 종목 전체)를 싣지 않는다 — 페이로드 비대화 방지.
// 상세 뷰의 '최근 매칭 종목'은 latest_matched(1일치)로 별도 수신.
export interface EdgeRuleDaily {
  id: number;
  rule_id: number;
  report_date: string;
  n_matched: number;
  mean_net_ret: number | null;
  created_at: string;
}

export interface EdgeRuleLatestMatched {
  report_date: string;
  matched: EdgeRuleMatched[] | null;
}

// 서버 페이지가 rule + 일별 시계열(+최신 매칭 1일치)을 함께 실어 카드/상세로 내려준다.
export type EdgeRuleWithDaily = EdgeRule & {
  daily: EdgeRuleDaily[];
  latest_matched: EdgeRuleLatestMatched | null;
};

// ── 스케줄러 잡 실행 이력 (workers/scheduler.py → job_run 테이블, admin 워커 현황) ──
export type JobRunStatus = 'running' | 'success' | 'fail' | 'timeout' | 'aborted';

export interface JobRun {
  id: number;
  job_name: string;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: JobRunStatus;
  exit_code: number | null;
  log_tail: string | null;
}

export interface JobRunsResponse {
  latest: JobRun[]; // 잡별 최신 1건
  runs: JobRun[];   // 최근 N일 이력(최신순)
}

// ── 거시 이벤트 캘린더 (macro_event 테이블 — /api/macro-events, trading 거시 게이트와 공유) ──
export interface MacroEvent {
  date: string; // YYYY-MM-DD (발표/결정일, KST)
  time: string; // HH:MM (KST)
  name: string; // "FOMC 금리결정" / "미 CPI" / "한은 금통위" …
  category: string; // rate | inflation | employment | other
  severity: number; // 3=중대(전야 자동매매 시드 축소) / 2=주의(관찰)
}

export interface MacroEventsResponse {
  events: MacroEvent[];
}
