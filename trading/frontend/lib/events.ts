// 감사 이벤트(audit_log) 렌더링 메타 — 모니터 탭(폴링 활동 로그)과 청산 종목 워커 로그 모달이 공유한다.
// 새 이벤트가 생기면 여기에만 추가하면 양쪽에 반영된다.

export type EventMeta = { label: string; tone: string };

const NEUTRAL = "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
const MUTED = "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400";
const RED = "bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400";
const BUY = "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400";
const SELL = "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400";

const EVENT_META: Record<string, EventMeta> = {
  // 매수 집행
  buy_start: { label: "매수 시작", tone: NEUTRAL },
  buy_exec: { label: "매수 집행", tone: BUY },
  buy_intended: { label: "매수 주문", tone: NEUTRAL },
  buy_retry_intended: { label: "매수 재주문", tone: NEUTRAL },
  buy_filled_paper: { label: "매수 체결", tone: BUY },
  buy_filled_live: { label: "매수 체결", tone: BUY },
  buy_rejected: { label: "매수 거부", tone: RED },
  buy_skip: { label: "매수 스킵", tone: MUTED },
  buy_skipped: { label: "매수 스킵", tone: MUTED },
  buy_blocked: { label: "매수 차단", tone: MUTED },
  manual_buy_link: { label: "수동 매수", tone: BUY },
  // 매도 모니터
  monitor_start: { label: "모니터 시작", tone: NEUTRAL },
  monitor_trail: { label: "스탑 상향", tone: "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400" },
  monitor_stop: { label: "스탑 발동", tone: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400" },
  monitor_hardstop: { label: "하드손절", tone: RED },
  // 매도 집행
  sell_intended: { label: "매도 주문", tone: NEUTRAL },
  sell_rejected: { label: "매도 거부", tone: RED },
  sell_filled_paper: { label: "매도 체결", tone: SELL },
  sell_filled_live: { label: "매도 체결", tone: SELL },
};

/** 이벤트명 → 라벨/색. 미정의 이벤트는 이벤트명 그대로(중립색) 노출해 누락이 없게 한다. */
export function eventMeta(event: string): EventMeta {
  return EVENT_META[event] ?? { label: event, tone: NEUTRAL };
}

function num(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString() : "-";
}

/** payload → 한 줄 설명. 모니터 탭과 워커 로그 모달이 공유. 모르는 이벤트는 빈 문자열. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function eventDetail(event: string, payload: any): string {
  const p = payload ?? {};
  switch (event) {
    case "monitor_start":
      return `폴링 ${p.poll_sec ?? "?"}s · 손절 −${p.hard_stop_pct ?? "?"}% · 트레일링 −${p.trail_pct ?? "?"}%`;
    case "monitor_trail":
      return `스탑 ${num(p.old)} → ${num(p.new)} (현재가 ${num(p.cur)})`;
    case "monitor_stop":
      return `현재가 ${num(p.cur)} ≤ 스탑 ${num(p.stop)} · ${p.sent ? "매도 전송" : "전송 안 됨"}`;
    case "monitor_hardstop":
      return `현재가 ${num(p.cur)} ≤ 손절 ${num(p.hard_stop)} · ${p.sent ? "매도 전송" : "전송 안 됨"}`;
    case "buy_start":
      return `${(p.exchange ?? p.venue ?? "").toString().toUpperCase()} ${p.window ?? ""} · 눌림 −${p.pullback_pct ?? "?"}%`;
    case "buy_exec":
      return `${num(p.shares)}주 @${num(p.price)} · ${p.sent ? "매수 전송" : p.error ? "실패" : "전송 안 됨"}${
        p.reason && String(p.reason).includes("데드라인") ? " (데드라인)" : ""
      }`;
    case "buy_intended":
    case "buy_retry_intended":
      return `${num(p.qty)}주 @${num(p.price)} 주문`;
    case "buy_filled_paper":
    case "buy_filled_live":
      return `${num(p.qty)}주 @${num(p.price)} 체결`;
    case "manual_buy_link":
      return `${num(p.qty)}주 @${num(p.avg_price)} 수동 매수 연동${p.reason ? ` · ${p.reason}` : ""}`;
    case "buy_skip":
      return p.reason === "blocklist" ? "blocklist 제외" : `${p.reason ?? "스킵"}`;
    case "buy_skipped":
    case "buy_blocked":
      return `${p.reason ?? "스킵"}`;
    case "buy_rejected":
    case "sell_rejected":
      return "주문 거부";
    case "sell_intended":
      return `${num(p.qty)}주 @${num(p.price)} 주문${p.tag ? ` · ${p.tag}` : ""}`;
    case "sell_filled_paper":
      return `${num(p.qty)}주 @${num(p.price)} 체결 · 실현 ${num(p.realized)}원`;
    case "sell_filled_live":
      return `${num(p.qty)}주 @${num(p.price)} 체결 · 실현 ${num(p.realized)}원 (수수료 ${num(p.cmsn)}·세금 ${num(p.tax)})`;
    default:
      return "";
  }
}
