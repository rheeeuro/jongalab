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
}

export interface MarketIndices {
  US: MarketIndex[];
  KR: MarketIndex[];
  COMMODITIES: MarketIndex[];
  FUTURES: MarketIndex[];
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
  news_headlines?: string[];        // 최근 헤드라인 목록
  score: number;
  reason: string;  // 종합 점수 구성요소로 자동 생성된 매수 이유
  rank_no: number;
  gap_nxt_price?: number | null;
  gap_nxt_pct?: number | null;
  gap_krx_price?: number | null;
  gap_krx_pct?: number | null;
  gap_checked_at?: string | null;
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

export interface NewsHeatItem {
  ticker: string;
  company_name: string | null;
  mention_count: number;
  last_at: string | null;
}

// 종목별 당일 뉴스 헤드라인 (/api/news/{ticker}, news_mention 원천)
export interface NewsMentionItem {
  headline: string;
  source_url: string | null;
  channel_name: string | null;
  created_at: string | null;
}

export interface StockReportDetail {
  report: StockReport;
  content_analyses?: ContentAnalysisItem[];
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
  ci_low: number | null;        // 단측 95% 신뢰구간 하한 — 승격 게이트(>0)
  worst_low_ret: number | null; // 매칭 종목 익일 저가 최악값(꼬리)
  updated_through: string | null;
  recent_n?: number;
  recent_mean_net?: number | null;
  // 승격 게이트(core/edge_policy.check_promotion) 통과 여부 — 평가기가 계산해 저장.
  // 프론트는 이 값을 렌더링만 한다(조건을 프론트에서 재계산하지 않음 — 단일 소스).
  promo_eligible?: boolean;
}

export interface PredicateCond {
  col: string;
  op: string;
  value?: unknown;
}

export interface EdgeRule {
  id: number;
  name: string;
  title: string | null;        // 카드 제목(한글) — NULL 이면 name 슬러그 폴백
  family: string;              // 도메인: f1_news / f2_global / f3_nxt / f4_laggard / f5_supply / f6_ah / control
  role: 'selector' | 'veto' | 'benchmark';  // 역할: 선정 / 위험 회피(제외 전용) / 측정·기준선
  description: string;
  predicate: PredicateCond[];
  exit_label: string;
  status: 'candidate' | 'live' | 'retired';
  min_sample: number;
  registered_at: string;
  stats: EdgeRuleStats | null;
  created_at: string;
  promoted_at: string | null;
  retired_at: string | null;
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
