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
  score: number;
  reason: string;  // 종합 점수 구성요소로 자동 생성된 매수 이유
  rank_no: number;
  gap_nxt_price?: number | null;
  gap_nxt_pct?: number | null;
  gap_krx_price?: number | null;
  gap_krx_pct?: number | null;
  gap_checked_at?: string | null;
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
  status: 'pending' | 'approved' | 'rejected' | 'expired';
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
