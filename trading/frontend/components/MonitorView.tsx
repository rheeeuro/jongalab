"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import type { MonitorState, MonitorPosition, NameMap, BuyPreview, BuyPreviewVenue, RegimeGateDiag } from "@/types";
import { won, wonExact, pnlClass, ago, hhmmss } from "@/lib/format";
import { eventMeta, eventDetail } from "@/lib/events";

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

// 현재가가 스탑/손절선 위로 얼마나 떨어져 있는지(%). 양수=안전 여유, 음수=이미 이탈.
function gapPct(cur: number, line: number): number | null {
  if (!cur || !line) return null;
  return ((cur - line) / cur) * 100;
}

export default function MonitorView({ initial, names }: { initial: MonitorState; names: NameMap }) {
  const [data, setData] = useState<MonitorState>(initial);
  const [preview, setPreview] = useState<BuyPreview | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [refreshing, setRefreshing] = useState(false);
  const nm = (c: string | null) => (c ? names[c] || c : "");
  const live = data.active || data.in_window; // 가동 중이거나 가동 구간이면 실시간 폴링
  // 매수 집행 단계에선 '보유 종목·스탑' 대신 이 워커가 곧 살 '매수 예정 종목'을 보여준다.
  const isBuyPhase = data.phase === "buy_krx" || data.phase === "buy_nxt";
  const buyExchange = data.phase === "buy_nxt" ? "NXT" : "KRX"; // 현재 매수 워커가 담당하는 거래소

  // 폴링/수동 새로고침이 공유하는 fetch — 일시 오류는 다음 호출에서 회복(조용히 무시).
  const fetchMonitor = useCallback(async () => {
    try {
      const res = await fetch("/api/monitor", { cache: "no-store" });
      if (res.ok) setData(await res.json());
    } catch {
      /* noop */
    }
  }, []);
  const fetchPreview = useCallback(async () => {
    try {
      const res = await fetch("/api/buy-preview", { cache: "no-store" });
      if (res.ok) setPreview(await res.json());
    } catch {
      /* noop */
    }
  }, []);

  // 수동 새로고침 — 현재 단계에 맞는 데이터를 즉시 다시 불러온다(폴링을 기다리지 않음).
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([fetchMonitor(), ...(isBuyPhase ? [fetchPreview()] : [])]);
    } finally {
      setRefreshing(false);
    }
  }, [fetchMonitor, fetchPreview, isBuyPhase]);

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
    const t = setInterval(fetchMonitor, ms);
    return () => clearInterval(t);
  }, [live, data.poll_sec, fetchMonitor]);

  // 매수 단계에서만 매수 예정 종목을 폴링(즉시 1회 + 폴링 주기). 비매수 단계면 폴링하지 않는다
  // (preview 는 매수 단계에서만 렌더되므로 굳이 비우지 않는다 — 다음 진입 시 즉시 새로 불러온다).
  useEffect(() => {
    if (!isBuyPhase) return;
    // 진입 즉시 1회 + 폴링. setState 는 fetch 해소 후 비동기로 일어나므로 cascading render 아님.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchPreview();
    const t = setInterval(fetchPreview, Math.max((data.poll_sec || 15) * 1000, 5000));
    return () => clearInterval(t);
  }, [isBuyPhase, data.poll_sec, fetchPreview]);

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
          <div className="flex shrink-0 items-center gap-1.5">
            <span className="text-xs text-slate-400 tabular-nums">
              {data.last_poll_at ? `마지막 폴링 ${ago(data.last_poll_at, nowMs)}` : "폴링 기록 없음"}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              aria-label="새로고침"
              className="grid h-9 w-9 place-items-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 active:bg-slate-200 disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </button>
          </div>
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

      {/* 매수 집행 단계 — 이 워커가 곧 살 매수 예정 종목(현재 거래소 몫). 보유·스탑 대신 노출. */}
      {isBuyPhase && (
        <BuyPreviewSection preview={preview} exchange={buyExchange} nm={nm} />
      )}

      {/* 보유 종목 + 스탑선/손절가 — 매도 감시 등 비매수 단계에서만 (매수 중엔 무의미) */}
      {!isBuyPhase && (
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
                  {/* 손절가·스탑선·평단·현재가 게이지 */}
                  <PositionGauge p={p} />
                </li>
              );
            })}
          </ul>
        )}
      </section>
      )}

      {/* 폴링 활동 로그 */}
      <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <h2 className="mb-1 text-base font-bold">폴링 활동 로그</h2>
        {events.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">아직 기록된 폴링 활동이 없어요.</p>
        ) : (
          <ul className="space-y-3">
            {events.map((e) => {
              const meta = eventMeta(e.event);
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
                    <p className="mt-0.5 text-xs text-slate-400 tabular-nums">{eventDetail(e.event, e.payload)}</p>
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

// 손절가·스탑선·평단·현재가를 하나의 가격축 게이지로 압축 표시.
// 트랙 = [최저값, 최고값]에 여백을 준 가격 범위. 왼쪽(빨강)=위험 구간(스탑 이하),
// 스탑→현재 사이(emerald)=남은 여유. 현재가 노브는 손익 방향으로 채색(이익 rose/손실 blue).
function PositionGauge({ p }: { p: MonitorPosition }) {
  // hover(데스크탑)/탭(모바일)한 마커의 key — 툴팁으로 라벨·값을 표시
  const [active, setActive] = useState<string | null>(null);
  const cur = p.cur_prc ?? 0;
  const avg = p.avg_price;
  const hard = p.hard_stop;
  const trail = p.plan_active ? p.stop_price : null; // 활성 청산계획 없으면 트레일링 미확정
  const vals = [cur, avg, hard, trail].filter((v): v is number => typeof v === "number" && v > 0);

  // 손절/스탑 가격 캡션 (게이지를 못 그려도 최소 정보는 유지)
  const hardGap = gapPct(cur, hard);
  const trailGap = trail ? gapPct(cur, trail) : null;
  const gapChip = (g: number | null) =>
    g == null ? null : (
      <span className={g < 0 ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"}>
        {g < 0 ? "이탈 " : "여유 "}
        {Math.abs(g).toFixed(1)}%
      </span>
    );

  const caption = (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] tabular-nums text-slate-400">
      <span className="flex items-center gap-1">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500" />
        손절 {wonExact(hard)} {gapChip(hardGap)}
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />
        {trail ? (
          <>
            스탑 {wonExact(trail)} {gapChip(trailGap)}
          </>
        ) : (
          <span className="text-slate-400">스탑 장 시작 전</span>
        )}
      </span>
    </div>
  );

  // 값이 부족하거나 현재가 미조회면 게이지 생략, 캡션만.
  if (vals.length < 2 || !cur) return caption;

  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo;
  const pad = span > 0 ? span * 0.15 : hi * 0.02 || 1;
  const dLo = lo - pad;
  const dHi = hi + pad;
  const at = (v: number) => Math.min(100, Math.max(0, ((v - dLo) / (dHi - dLo)) * 100));

  const effStop = trail != null ? Math.max(hard, trail) : hard; // 먼저 닿는(=높은) 스탑이 실질 청산선
  const curPct = at(cur);
  const avgPct = at(avg);
  const stopPct = at(effStop);
  const up = cur >= avg; // 손익 방향 (한국 관례)

  // 각 지점 — hover/탭 시 라벨·값·현재가 대비 여유를 툴팁으로 노출
  const markers = [
    { key: "hard", label: "손절가", value: hard, pct: at(hard), dot: "bg-red-500", gap: hardGap },
    ...(trail != null
      ? [{ key: "trail", label: "스탑선", value: trail, pct: at(trail), dot: "bg-amber-500", gap: trailGap }]
      : []),
    { key: "avg", label: "평단", value: avg, pct: avgPct, dot: "bg-slate-400", gap: gapPct(cur, avg) },
    { key: "cur", label: "현재가", value: cur, pct: curPct, dot: up ? "bg-rose-500" : "bg-blue-500", gap: null },
  ];
  const activeM = markers.find((m) => m.key === active) ?? null;
  // 툴팁이 트랙 좌/우 끝을 넘어가지 않도록 정렬 보정
  const tipX = (pct: number) => (pct < 15 ? "0" : pct > 85 ? "-100%" : "-50%");
  const clear = (key: string) => setActive((a) => (a === key ? null : a));

  return (
    <div className="mt-3">
      <div className="relative h-2 rounded-full bg-slate-100 dark:bg-slate-800">
        {/* 위험 구간: 실질 청산선(스탑) 이하 */}
        <div
          className="absolute inset-y-0 left-0 rounded-l-full bg-red-400/50 dark:bg-red-500/40"
          style={{ width: `${stopPct}%` }}
        />
        {/* 여유 구간: 스탑 → 현재가 (상승 시에만 의미) */}
        {curPct > stopPct && (
          <div
            className="absolute inset-y-0 bg-emerald-400/60 dark:bg-emerald-500/40"
            style={{ left: `${stopPct}%`, width: `${curPct - stopPct}%` }}
          />
        )}
        {/* 평단 (손익분기) — 점선 세로선 */}
        <div
          className="pointer-events-none absolute -top-1 -bottom-1 w-0 border-l border-dashed border-slate-400 dark:border-slate-500"
          style={{ left: `${avgPct}%` }}
        />
        {/* 손절가 틱 */}
        <div
          className="pointer-events-none absolute -top-0.5 -bottom-0.5 w-0.5 -translate-x-1/2 rounded bg-red-500"
          style={{ left: `${at(hard)}%` }}
        />
        {/* 스탑선 틱 */}
        {trail != null && (
          <div
            className="pointer-events-none absolute -top-0.5 -bottom-0.5 w-0.5 -translate-x-1/2 rounded bg-amber-500"
            style={{ left: `${at(trail)}%` }}
          />
        )}
        {/* 현재가 노브 */}
        <div
          className={`pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow transition-transform dark:border-slate-900 ${
            up ? "bg-rose-500" : "bg-blue-500"
          } ${active === "cur" ? "scale-125" : ""}`}
          style={{ left: `${curPct}%` }}
        />

        {/* 넓은 히트 타깃 (틱/노브는 얇으므로 별도 오버레이로 hover/탭 수신) */}
        {markers.map((m) => (
          <button
            key={m.key}
            type="button"
            aria-label={`${m.label} ${wonExact(m.value)}`}
            className="absolute top-1/2 z-[1] h-6 w-7 -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${m.pct}%` }}
            onMouseEnter={() => setActive(m.key)}
            onMouseLeave={() => clear(m.key)}
            onFocus={() => setActive(m.key)}
            onBlur={() => clear(m.key)}
            onClick={() => setActive((a) => (a === m.key ? null : m.key))}
          />
        ))}

        {/* 툴팁 */}
        {activeM && (
          <div
            className="pointer-events-none absolute bottom-full z-10 mb-2 flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-slate-800 px-2 py-1 text-[11px] font-medium text-white shadow-lg dark:bg-slate-700"
            style={{ left: `${activeM.pct}%`, transform: `translateX(${tipX(activeM.pct)})` }}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${activeM.dot}`} />
            <span className="text-slate-300">{activeM.label}</span>
            <span className="tabular-nums">{wonExact(activeM.value)}</span>
            {activeM.gap != null && (
              <span className={`tabular-nums ${activeM.gap < 0 ? "text-red-300" : "text-emerald-300"}`}>
                {activeM.gap < 0 ? "이탈 " : "여유 "}
                {Math.abs(activeM.gap).toFixed(1)}%
              </span>
            )}
          </div>
        )}
      </div>
      {caption}
    </div>
  );
}

// 매수 예정 목록의 시드 축소 사유(레짐·선물 게이트) — 왜 시드/수량이 줄었는지 한 줄로.
function GateNotes({ regime, venue }: { regime: RegimeGateDiag; venue: BuyPreviewVenue }) {
  const sp = (v?: number) => (typeof v === "number" ? `${v >= 0 ? "+" : ""}${v}` : "-");

  const regimeLine =
    regime && regime.multiplier < 1
      ? `레짐 ×${regime.multiplier} · 점수 판별력 ${regime.inverted ? "역전" : "약화"} → 시드 ${wonExact(
          venue.seed_base,
        )}→${wonExact(venue.seed)}`
      : null;

  let futuresLine: string | null = null;
  const f = venue.futures;
  if (f?.gated) {
    const kospi = f.kospi_label ?? "코스피선물";
    const env = `NQ ${sp(f.nq_pct)}%${f.nq_down ? "↓" : ""} · ${kospi} ${sp(f.kospi_pct)}%${f.kospi_down ? "↓" : ""}`;
    futuresLine = f.nq_down || f.kospi_down ? `선물 ${env} → 섹터 감액` : `선물 ${env} · 감액 없음`;
  } else if (f && f.reason === "unavailable") {
    // NXT 는 야간선물 개장(18:00) 전이면 흔히 미취득 — 안내. KRX 는 일반 미취득.
    futuresLine =
      venue.exchange === "NXT"
        ? "선물 게이트 · 야간선물 대기 (19:50 집행 시 반영)"
        : "선물 게이트 · 지표 대기 (집행 시 반영)";
  }

  if (!regimeLine && !futuresLine) return null;
  return (
    <div className="mb-2 space-y-0.5">
      {regimeLine && <p className="text-[11px] leading-tight text-amber-600 dark:text-amber-400">{regimeLine}</p>}
      {futuresLine && <p className="text-[11px] leading-tight text-amber-600 dark:text-amber-400">{futuresLine}</p>}
    </div>
  );
}

// 매수 집행 단계 전용 — 현재 거래소(KRX/NXT) 몫의 매수 예정 종목·예상 수량(실시간 미리보기).
function BuyPreviewSection({
  preview,
  exchange,
  nm,
}: {
  preview: BuyPreview | null;
  exchange: "KRX" | "NXT";
  nm: (c: string | null) => string;
}) {
  const venue = preview?.venues.find((v) => v.exchange === exchange) ?? null;
  const stocks = venue?.stocks ?? [];
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h2 className="text-base font-bold">매수 예정</h2>
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-bold leading-none ${
              exchange === "NXT"
                ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300"
                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            }`}
          >
            {exchange}
          </span>
        </div>
        {venue && (
          <span className="text-sm font-medium text-slate-400 tabular-nums">{venue.count}종목</span>
        )}
      </div>
      {venue ? (
        <p className="-mt-0.5 mb-1 text-xs text-slate-400 tabular-nums">
          {venue.window} · 시드 {wonExact(venue.seed)}
        </p>
      ) : null}
      {venue && preview ? <GateNotes regime={preview.regime} venue={venue} /> : null}
      {!preview ? (
        <p className="py-6 text-center text-sm text-slate-400">매수 예정 종목을 불러오는 중…</p>
      ) : stocks.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">이 거래소 매수 예정 종목이 없어요.</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {stocks.map((s) => {
            const buying = s.shares >= 1;
            return (
              <li
                key={s.stk_cd}
                className={`flex items-center justify-between gap-2 py-3 ${buying ? "" : "opacity-50"}`}
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 truncate font-semibold">
                    {s.rank_no != null && (
                      <span className="shrink-0 text-xs font-bold text-slate-400 tabular-nums">
                        {s.rank_no}
                      </span>
                    )}
                    <span className="truncate">{nm(s.stk_cd)}</span>
                  </p>
                  <p className="text-xs text-slate-400 tabular-nums">
                    {s.stk_cd} · {s.score.toFixed(1)}점
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  {buying ? (
                    <>
                      <p className="font-semibold tabular-nums">{s.shares}주</p>
                      <p className="text-xs text-slate-400 tabular-nums">{wonExact(s.cost)}</p>
                      {s.keep != null && (
                        <p className="text-[10px] font-bold text-amber-600 tabular-nums dark:text-amber-400">
                          선물 ×{s.keep}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-xs font-medium text-slate-400">{s.note ?? "매수 안 함"}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
