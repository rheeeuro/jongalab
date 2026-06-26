"use client";

import { useEffect, useRef, useState } from "react";
import type { MonitorState, MonitorEvent, NameMap } from "@/types";
import { won, wonExact, pnlClass, ago, hhmmss } from "@/lib/format";

// 폴링으로 새로 들어온 항목의 id 집합을 반환 — 첫 로드분은 제외(자동 채워진 것만 애니메이션).
// 항목 배열(items)의 참조가 바뀔 때만(=폴링 갱신 시) 비교한다. 1초 틱 리렌더에는 반응하지 않음.
function useNewIds<T extends { id: number }>(items: T[]): Set<number> {
  const seen = useRef<Set<number> | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  useEffect(() => {
    const ids = items.map((i) => i.id);
    if (seen.current === null) {
      seen.current = new Set(ids); // 첫 로드: 전부 '본 것'으로 등록(애니메이션 없음)
      return;
    }
    const added = ids.filter((id) => !seen.current!.has(id));
    if (added.length === 0) return;
    added.forEach((id) => seen.current!.add(id));
    setFresh(new Set(added));
    const t = setTimeout(() => setFresh(new Set()), 1600); // 애니메이션(1.4s) 후 표식 해제
    return () => clearTimeout(t);
  }, [items]);
  return fresh;
}

const ORDER_STATUS: Record<string, string> = {
  filled: "체결", sent: "전송", intended: "접수", rejected: "거부",
  canceled: "취소", accepted: "수락",
};

const EVENT_META: Record<MonitorEvent["event"], { label: string; tone: string }> = {
  monitor_start: { label: "모니터 시작", tone: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  monitor_trail: { label: "스탑 상향", tone: "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400" },
  monitor_stop: { label: "스탑 발동", tone: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400" },
  monitor_hardstop: { label: "하드손절", tone: "bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400" },
  buy_start: { label: "매수 시작", tone: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  buy_exec: { label: "매수 집행", tone: "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400" },
  buy_skip: { label: "매수 스킵", tone: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
};

// 현재가가 스탑/손절선 위로 얼마나 떨어져 있는지(%). 양수=안전 여유, 음수=이미 이탈.
function gapPct(cur: number, line: number): number | null {
  if (!cur || !line) return null;
  return ((cur - line) / cur) * 100;
}

export default function MonitorView({ initial, names }: { initial: MonitorState; names: NameMap }) {
  const [data, setData] = useState<MonitorState>(initial);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const nm = (c: string | null) => (c ? names[c] || c : "");
  const live = data.active || data.in_window; // 가동 중이거나 가동 구간이면 실시간 폴링

  // 1초 틱 — '마지막 폴링 n초 전' 라벨 갱신
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // /api/monitor 주기 재조회 — 가동 중엔 폴링 주기(15초), 유휴 시엔 keep-alive(60초).
  // 유휴 폴링이 윈도우 시작/하트비트를 감지하면 live 가 true 로 바뀌어 자동으로 15초 모드로 전환된다
  // (탭을 종일 띄워둬도 08:00·15:00·19:30 에 새로고침 없이 깨어남).
  useEffect(() => {
    const ms = live ? Math.max((data.poll_sec || 15) * 1000, 5000) : 60_000;
    const t = setInterval(async () => {
      try {
        const res = await fetch("/api/monitor", { cache: "no-store" });
        if (res.ok) setData(await res.json());
      } catch {
        /* 일시 오류는 다음 폴링에서 회복 */
      }
    }, ms);
    return () => clearInterval(t);
  }, [live, data.poll_sec]);

  const positions = data.positions ?? [];
  const orders = data.orders ?? [];
  const events = data.events ?? [];

  // 폴링으로 새로 들어온 로그/주문에 진입 애니메이션 표식
  const newEventIds = useNewIds(events);
  const newOrderIds = useNewIds(orders);

  const phaseLabel =
    data.phase === "sell" ? "매도 감시"
    : data.phase === "buy_krx" ? "매수 집행 · KRX"
    : data.phase === "buy_nxt" ? "매수 집행 · NXT"
    : null;
  const statusTitle = data.active
    ? phaseLabel ? `${phaseLabel} 중` : "폴링 가동 중"
    : data.in_window ? "신호 없음" : "모니터 대기";
  const isBuyPhase = data.phase === "buy_krx" || data.phase === "buy_nxt";
  const activeDesc = isBuyPhase
    ? `${data.poll_sec}초마다 매수 후보를 점검 중이에요. 고점 대비 −${data.pullback_pct}% 눌리면 매수해요.`
    : `${data.poll_sec}초마다 보유 종목을 점검 중이에요. 손절 −${data.hard_stop_pct}% · 트레일링 −${data.trail_pct}%.`;

  return (
    <div className="space-y-4">
      {/* 상태 헤더 */}
      <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span
              className={`relative flex h-2.5 w-2.5 shrink-0 ${
                data.active ? "" : "opacity-60"
              }`}
            >
              {data.active && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              )}
              <span
                className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                  data.active ? "bg-emerald-500" : data.in_window ? "bg-amber-500" : "bg-slate-400"
                }`}
              />
            </span>
            <span className="truncate text-base font-bold">{statusTitle}</span>
          </div>
          <span className="shrink-0 text-xs text-slate-400 tabular-nums">
            {data.last_poll_at ? `마지막 폴링 ${ago(data.last_poll_at, nowMs)}` : "폴링 기록 없음"}
          </span>
        </div>
        {data.active && data.worker && (
          <p className="mt-1.5">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {data.worker}
            </code>
          </p>
        )}
        <p className="mt-2 text-xs leading-relaxed text-slate-400">
          {data.active
            ? activeDesc
            : data.in_window
              ? "가동 구간인데 폴링 신호가 없어요. 워커 상태를 확인하세요."
              : "폴링은 평일 매도 08:00~09:30 · 매수 15:00·19:30에만 가동돼요. 지금은 마지막 상태를 보여줍니다."}
        </p>
      </section>

      {/* 보유 종목 + 스탑선/손절가 */}
      <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-base font-bold">보유 종목 · 스탑</h2>
          {positions.length > 0 && (
            <span className="text-sm font-medium text-slate-400 tabular-nums">{positions.length}종목</span>
          )}
        </div>
        {positions.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">보유 중인 종목이 없어요.</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {positions.map((p) => {
              const up = p.unrealized_pnl ?? 0;
              const hardGap = gapPct(p.cur_prc ?? 0, p.hard_stop);
              const stopGap = p.stop_price ? gapPct(p.cur_prc ?? 0, p.stop_price) : null;
              return (
                <li key={p.stk_cd} className="py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{nm(p.stk_cd)}</p>
                      <p className="text-xs text-slate-400 tabular-nums">
                        {p.qty}주 · 평단 {wonExact(p.avg_price)}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="flex items-center justify-end gap-1 font-semibold tabular-nums">
                        {p.is_nxt && p.cur_prc ? (
                          <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-bold leading-none text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                            NXT
                          </span>
                        ) : null}
                        {p.cur_prc ? wonExact(p.cur_prc) : "-"}
                      </p>
                      <p className={`text-xs font-semibold tabular-nums ${pnlClass(up)}`}>{won(up)}</p>
                    </div>
                  </div>
                  {/* 스탑선 / 손절가 */}
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <StopPill
                      label="스탑선"
                      value={p.stop_price}
                      gap={stopGap}
                      pending={!p.plan_active}
                      pendingText="장 시작 전"
                    />
                    <StopPill label="손절가" value={p.hard_stop} gap={hardGap} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 폴링 활동 로그 */}
      <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <h2 className="mb-1 text-base font-bold">폴링 활동 로그</h2>
        {events.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">아직 기록된 폴링 활동이 없어요.</p>
        ) : (
          <ul className="space-y-3">
            {events.map((e) => {
              const meta = EVENT_META[e.event];
              return (
                <li
                  key={e.id}
                  className={`flex items-start gap-2.5 ${newEventIds.has(e.id) ? "animate-log-enter" : ""}`}
                >
                  <span className="mt-0.5 w-[52px] shrink-0 text-xs text-slate-400 tabular-nums">
                    {hhmmss(e.created_at)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold leading-none ${meta.tone}`}>
                        {meta.label}
                      </span>
                      {e.stk_cd && <span className="truncate text-sm font-semibold">{nm(e.stk_cd)}</span>}
                    </div>
                    <p className="mt-0.5 text-xs text-slate-400 tabular-nums">{eventDetail(e)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 주문 로그 */}
      <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <h2 className="mb-1 text-base font-bold">오늘 주문 로그</h2>
        {orders.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">오늘 주문이 없어요.</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {orders.map((o) => {
              const buy = o.side === "buy";
              const filled = o.status === "filled";
              return (
                <li
                  key={o.id}
                  className={`flex items-center justify-between gap-2 py-3 ${filled ? "" : "opacity-50"} ${
                    newOrderIds.has(o.id) ? "animate-log-enter" : ""
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span
                      className={`shrink-0 rounded-lg px-2 py-1 text-xs font-bold ${
                        buy
                          ? "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400"
                          : "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400"
                      }`}
                    >
                      {buy ? "매수" : "매도"}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{nm(o.stk_cd)}</p>
                      <p className="text-xs text-slate-400 tabular-nums">
                        {hhmmss(o.created_at)} · {ORDER_STATUS[o.status] ?? o.status}
                        {o.mode === "paper" ? " · 모의" : ""}
                      </p>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-semibold tabular-nums">{o.filled_qty || o.qty}주</p>
                    <p className="text-xs text-slate-400 tabular-nums">{wonExact(o.fill_price ?? o.price)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function StopPill({
  label,
  value,
  gap,
  pending,
  pendingText,
}: {
  label: string;
  value: number | null;
  gap: number | null;
  pending?: boolean;
  pendingText?: string;
}) {
  if (pending || value == null) {
    return (
      <div className="rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/50">
        <p className="text-[11px] text-slate-400">{label}</p>
        <p className="text-sm font-semibold text-slate-400">{pendingText ?? "—"}</p>
      </div>
    );
  }
  // gap<0 = 현재가가 이미 스탑선 아래(이탈) → 경고색
  const breached = gap != null && gap < 0;
  return (
    <div
      className={`rounded-xl px-3 py-2 ${
        breached ? "bg-red-50 dark:bg-red-950/30" : "bg-slate-50 dark:bg-slate-800/50"
      }`}
    >
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="text-sm font-semibold tabular-nums">{wonExact(value)}</p>
      {gap != null && (
        <p className={`text-[11px] tabular-nums ${breached ? "text-red-500" : "text-slate-400"}`}>
          현재가 대비 {gap >= 0 ? "+" : ""}
          {gap.toFixed(1)}%
        </p>
      )}
    </div>
  );
}

function eventDetail(e: MonitorEvent): string {
  const p = e.payload ?? {};
  switch (e.event) {
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
    case "buy_skip":
      return p.reason === "blocklist" ? "blocklist 제외" : `${p.reason ?? "스킵"}`;
    default:
      return "";
  }
}

function num(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString() : "-";
}
