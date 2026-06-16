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
}

export interface TradeSignal {
  id: number;
  trade_date: string;
  stk_cd: string;
  stk_nm: string | null;
  rank_no: number | null;
  score: number | null;
  status: "pending" | "executing" | "done" | "rejected" | "expired";
  note: string | null;
}
