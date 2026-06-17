/** trading 백엔드 응답 shape — 백엔드 repository/스키마와 일치시킨다. */

export interface HealthStatus {
  status: string;
  service: string;
  db: boolean;
  has_token: boolean;
  mode: "paper" | "live";
  kill_switch: boolean | null;
}

export interface Position {
  stk_cd: string;
  qty: number;
  avg_price: number;
  realized_pnl: number;
  updated_at: string;
  // /positions 에서 현재가로 평가 (조회 실패 시 0)
  cur_prc?: number;
  eval_amt?: number;
  unrealized_pnl?: number;
}

export type SignalStatus =
  | "pending"
  | "executing"
  | "done"
  | "skipped"
  | "rejected"
  | "expired";

export interface TradeSignal {
  id: number;
  trade_date: string;
  stk_cd: string;
  stk_nm: string | null;
  rank_no: number | null;
  score: number | null;
  status: SignalStatus;
  note: string | null;
}

export interface Order {
  id: number;
  stk_cd: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  mode: "paper" | "live";
  status: "intended" | "sent" | "accepted" | "rejected" | "filled" | "canceled";
  kiwoom_ord_no: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  event: string;
  stk_cd: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any;
  created_at: string;
}

export type NameMap = Record<string, string>;

export interface MonthlyPnl {
  month: string;
  total: number;
  days: Record<string, { realized_pnl: number; orders_count: number; breaker: boolean }>;
}

export interface DayPlan {
  stk_cd: string;
  gap_dir: "up" | "down";
  avg_price: number;
  nxt_open: number;
  stop_price: number;
  active: number;
}

export interface DayDetail {
  date: string;
  realized_pnl: number;
  orders_count: number;
  buys: Order[];
  sells: Order[];
  plans: DayPlan[];
  realized_by_stock: Record<string, number>;
}

export interface DailySummary {
  trade_date: string;
  realized_pnl: number;
  orders_count: number;
  breaker_tripped: boolean;
  open_positions: number;
  kill_switch: boolean | null;
}
