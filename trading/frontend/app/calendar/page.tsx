"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { won, wonExact, wonCompact, pnlClass, fmtDate } from "@/lib/format";
import type { MonthlyPnl, DayDetail, NameMap } from "@/types";

const WD = ["일", "월", "화", "수", "목", "금", "토"];

function nowMonth(): string {
  const n = new Date();
  return `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, "0")}`;
}

export default function CalendarPage() {
  const [month, setMonth] = useState(nowMonth());
  const [data, setData] = useState<MonthlyPnl | null>(null);
  const [names, setNames] = useState<NameMap>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<DayDetail | null>(null);
  const [loadingDay, setLoadingDay] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/names");
        if (r.ok) setNames(await r.json());
      } catch {
        /* ignore */
      }
    })();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`/api/pnl-monthly?month=${month}`);
        if (cancelled) return;
        setSelected(null);
        setDetail(null);
        setData(r.ok ? await r.json() : null);
      } catch {
        if (!cancelled) setData(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [month]);

  async function openDay(date: string) {
    setSelected(date);
    setLoadingDay(true);
    setDetail(null);
    try {
      const r = await fetch(`/api/day?date=${date}`);
      if (r.ok) setDetail(await r.json());
    } catch {
      /* ignore */
    } finally {
      setLoadingDay(false);
    }
  }

  function shiftMonth(delta: number) {
    const y = +month.slice(0, 4);
    const m = +month.slice(4, 6) - 1 + delta;
    const d = new Date(y, m, 1);
    setMonth(`${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const y = +month.slice(0, 4);
  const mo = +month.slice(4, 6);
  const firstDay = new Date(y, mo - 1, 1).getDay();
  const daysInMonth = new Date(y, mo, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const dayKey = (d: number) => `${month}${String(d).padStart(2, "0")}`;
  const nm = (c: string) => names[c] || c;

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="text-xl font-bold">손익 달력</h1>

      {/* 월 네비 + 합계 */}
      <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <button onClick={() => shiftMonth(-1)} aria-label="이전 달" className="rounded-full p-2 hover:bg-slate-100 dark:hover:bg-slate-800">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="text-base font-bold">{y}년 {mo}월</span>
          <button onClick={() => shiftMonth(1)} aria-label="다음 달" className="rounded-full p-2 hover:bg-slate-100 dark:hover:bg-slate-800">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-2 text-center">
          <p className="text-xs text-slate-400">이번 달 실현 손익</p>
          <p className={`text-2xl font-extrabold ${pnlClass(data?.total ?? 0)}`}>{won(data?.total ?? 0)}</p>
        </div>

        {/* 요일 */}
        <div className="mt-4 grid grid-cols-7 text-center text-xs text-slate-400">
          {WD.map((w, i) => (
            <div key={w} className={i === 0 ? "text-rose-400" : i === 6 ? "text-blue-400" : ""}>{w}</div>
          ))}
        </div>
        {/* 날짜 */}
        <div className="mt-1 grid grid-cols-7 gap-1">
          {cells.map((d, i) => {
            if (d === null) return <div key={`b${i}`} />;
            const key = dayKey(d);
            const info = data?.days?.[key];
            const v = info?.realized_pnl ?? 0;
            const has = !!info;
            const isSel = selected === key;
            return (
              <button
                key={key}
                onClick={() => openDay(key)}
                className={`flex aspect-square flex-col items-center justify-center rounded-xl transition-colors ${
                  isSel ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                <span className={`text-xs ${isSel ? "" : "text-slate-600 dark:text-slate-300"}`}>{d}</span>
                {has && v !== 0 && (
                  <span className={`mt-0.5 text-[9px] font-bold leading-none ${isSel ? "" : pnlClass(v)}`}>
                    {wonCompact(v)}
                  </span>
                )}
                {has && v === 0 && <span className="mt-0.5 text-[9px] leading-none text-slate-300">·</span>}
              </button>
            );
          })}
        </div>
      </section>

      {/* 선택 일자 상세 */}
      {selected && (
        <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold">{fmtDate(selected)}</h2>
            <span className={`text-base font-extrabold ${pnlClass(detail?.realized_pnl ?? 0)}`}>
              {won(detail?.realized_pnl ?? 0)}
            </span>
          </div>

          {loadingDay ? (
            <div className="flex min-h-[140px] items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : !detail || (detail.buys.length === 0 && detail.plans.length === 0) ? (
            <div className="flex min-h-[140px] items-center justify-center">
              <p className="text-sm text-slate-400">이 날의 매매 기록이 없어요.</p>
            </div>
          ) : (
            <div className="mt-3 space-y-4">
              {detail.buys.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-slate-400">매수</p>
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {detail.buys.map((o) => (
                      <li key={o.id} className="flex items-center justify-between py-2">
                        <span className="font-medium">{nm(o.stk_cd)}</span>
                        <span className="text-sm text-slate-500 tabular-nums">{o.qty}주 · {wonExact(o.price)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {detail.plans.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-slate-400">청산 (갭/손익)</p>
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {detail.plans.map((p) => {
                      const r = detail.realized_by_stock?.[p.stk_cd] ?? 0;
                      return (
                        <li key={p.stk_cd} className="flex items-center justify-between py-2">
                          <span className="flex items-center gap-2">
                            <span className="font-medium">{nm(p.stk_cd)}</span>
                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                              p.gap_dir === "up" ? "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400"
                                                 : "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400"}`}>
                              {p.gap_dir === "up" ? "갭상승" : "갭하락"}
                            </span>
                          </span>
                          <span className={`text-sm font-semibold tabular-nums ${pnlClass(r)}`}>{won(r)}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
