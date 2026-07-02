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
  // cur_prc 가 NXT(넥스트레이드) 보드 시세이면 true
  is_nxt?: boolean;
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
  /** 실제 체결 수량가중평균가. 미체결이면 null → price(주문 시점 참조가) 폴백. */
  fill_price: number | null;
  filled_qty: number;
  /** 스킵 행(주문 행 없음)은 mode 가 없다. */
  mode?: "paper" | "live";
  /** "skipped" 는 주문 행이 아닌 매수 스킵/차단(audit_log) — 거래내역 탭이 사유와 함께 표시. */
  status: "intended" | "sent" | "accepted" | "rejected" | "filled" | "canceled" | "skipped";
  kiwoom_ord_no: string | null;
  created_at: string;
  /** 체결 안 된 경우 사유 — 거부는 키움 메시지(예: "매수증거금이 부족합니다…"), 스킵은 스킵 사유, 체결분은 null. */
  reason?: string | null;
  /** "skip" = 주문 행이 아닌 매수 스킵/차단 항목(거래내역 병합용). 실제 주문이면 없음. */
  kind?: "skip";
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

/** 라운드트립 — 전일 매수 → 당일 매도 한 묶음 (얼마에 사서 얼마에 팔았나 + 실현손익). */
export interface RoundTrip {
  stk_cd: string;
  buy_date: string | null; // YYYYMMDD (직전 매수 거래일)
  buy_qty: number;
  buy_price: number;
  sell_qty: number;
  sell_price: number;
  realized: number; // 종목별 실현손익 (감사로그 권위값)
}

/** 1분봉 캔들 — 워커 로그 모달 차트(매수날 12시~매도날 12시). time 은 "YYYY-MM-DDTHH:MM". */
export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** 차트 매수/매도 타점 — 체결 이벤트(시각·가격)에서 만든다. time 은 가장 가까운 캔들로 스냅된다. */
export interface ChartMarker {
  time: string; // ISO 시각(이벤트 created_at)
  side: "buy" | "sell";
  price: number;
}

export interface DayDetail {
  date: string;
  realized_pnl: number;
  orders_count: number;
  buys: Order[];
  sells: Order[];
  plans: DayPlan[];
  realized_by_stock: Record<string, number>;
  roundtrips: RoundTrip[];
  invested: number; // 오늘 청산 원금(Σ 매수가×매도수량) — 실현손익 수익률의 분모
  fees: Fees; // 당일 수수료·세금
}

/** 당일 매매수수료·세금 합계(원). 실현손익(realized_pnl)은 이미 매도 측 수수료·세금이 차감된 순액. */
export interface Fees {
  cmsn: number; // 매매수수료
  tax: number; // 매매세금(매도)
  total: number; // cmsn + tax
}

/** 매수 예정 미리보기 — pending 시그널을 거래소별로 나눠 시드 배분·예상 수량을 계산(읽기 전용). */
export interface BuyPreviewStock {
  stk_cd: string;
  stk_nm: string | null;
  rank_no: number | null;
  score: number;
  price: number; // 호출 시점 현재가 (0이면 조회 실패)
  shares: number; // 예상 배분 수량 (게이트 반영 후)
  cost: number; // 예상 매수금액 (shares × price)
  keep: number | null; // 선물 섹터 게이트 keep-factor(<1이면 감액됨), 감액 없으면 null
  note: string | null; // "배분 0주(시드 부족)" / "현재가 없음" / "선물 게이트 감액" / null(매수 예정)
}

// 선물 섹터 게이트 진단 (buy-preview·audit 공유 shape)
export interface FuturesGateDiag {
  gated: boolean;
  reason?: string; // 미개입 사유 (unavailable / krx_skip / disabled …)
  nq_pct?: number;
  night_pct?: number;
  nq_down?: boolean;
  night_down?: boolean;
  night_note?: string;
}

// 롤링 엣지 게이트(레짐) 진단
export interface RegimeGateDiag {
  multiplier: number; // 총 시드 배수 (<1이면 축소)
  gated: boolean;
  split?: number; // 점수 스프레드(%p)
  inverted?: boolean;
  n?: number; // 표본 수
  reason?: string;
}

export interface BuyPreviewVenue {
  exchange: "KRX" | "NXT";
  window: string; // 매수 윈도우 (예: "15:00~15:20")
  seed_base: number; // 게이트 전 시드 (가용현금 × 점수비율)
  seed: number; // 레짐 게이트 반영 후 시드
  invested: number; // 예상 매수금액 합계 (선물 게이트 반영 후)
  count: number; // 실제 매수 예정 종목 수 (1주 이상)
  futures: FuturesGateDiag | null; // 선물 섹터 게이트 상태 (NXT만, KRX는 null)
  stocks: BuyPreviewStock[];
}

export interface BuyPreview {
  trade_date: string;
  cash: number; // 가용현금 (현금주문가능금액)
  total_score: number;
  regime: RegimeGateDiag; // 레짐 게이트(두 거래소 공통)
  venues: BuyPreviewVenue[];
}

/** 모니터 탭 — 폴링 워커 가동 상태 + 스탑선/손절가가 붙은 보유 포지션 + 활동/주문 로그. */
export interface MonitorPosition extends Position {
  hard_stop: number; // 손절가 = 평단 × (1 - HARD_STOP_LOSS_PCT/100)
  stop_price: number | null; // 스탑선(트레일링) — 활성 청산계획이 없으면 null(장 시작 전)
  plan_active: boolean; // 활성 청산계획(감시 대상) 여부
}

/** 폴링 활동 이벤트 — 매도(스탑 상향/발동·손절) + 매수(집행/스킵/시작). */
export type MonitorEventType =
  | "monitor_start"
  | "monitor_trail"
  | "monitor_stop"
  | "monitor_hardstop"
  | "buy_start"
  | "buy_exec"
  | "buy_skip";

export interface MonitorEvent {
  id: number;
  event: MonitorEventType;
  stk_cd: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any;
  created_at: string;
}

/** 현재 폴링 단계 — 매도 감시 / KRX·NXT 매수 집행 / 미가동(null). */
export type MonitorPhase = "sell" | "buy_krx" | "buy_nxt" | null;

export interface MonitorState {
  active: boolean; // 하트비트 기준 워커 가동 중 여부 (60초 이내 폴링)
  in_window: boolean; // 가동 구간(매도 08:00~09:30 / 매수 15:00·19:30) 여부
  phase: MonitorPhase; // 현재 폴링 단계
  worker: string | null; // 실제 폴링 중인 pm2 워커명 (예: trading-buy-nxt), 미가동 시 null
  last_poll_at: string | null; // 마지막 폴링 시각 (ISO)
  poll_sec: number; // 폴링 주기(초)
  hard_stop_pct: number; // 하드 손절 임계 %
  trail_pct: number; // 트레일링 되돌림 %
  pullback_pct: number; // 매수 눌림 임계 %
  positions: MonitorPosition[];
  orders: Order[];
  events: MonitorEvent[];
}

export interface DailySummary {
  trade_date: string;
  realized_pnl: number;
  orders_count: number;
  breaker_tripped: boolean;
  open_positions: number;
  kill_switch: boolean | null;
  fees: Fees; // 당일 수수료·세금
}
