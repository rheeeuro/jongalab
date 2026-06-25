"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { won, wonExact, wonCompact, pnlClass, fmtDate, todayYYYYMMDD } from "@/lib/format";
import type { MonthlyPnl, DayDetail, NameMap } from "@/types";
import RoundTrips from "@/components/RoundTrips";

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
    if (selected === date) {
      setSelected(null);
      setDetail(null);
      return;
    }
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
  while (cells.length % 7 !== 0) cells.push(null); // 마지막 주 패딩
  const weeks: (number | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  const dayKey = (d: number) => `${month}${String(d).padStart(2, "0")}`;
  const today = todayYYYYMMDD();
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
            const isToday = key === today;
            const isWeekend = i % 7 === 0 || i % 7 === 6; // 0=일, 6=토
            return (
              <button
                key={key}
                onClick={() => openDay(key)}
                disabled={isWeekend}
                className={`flex aspect-square flex-col items-center justify-center rounded-xl transition-colors ${
                  isWeekend
                    ? "cursor-not-allowed opacity-40"
                    : isSel
                    ? "bg-slate-200 dark:bg-slate-700"
                    : isToday
                    ? "ring-1 ring-inset ring-amber-400 dark:ring-amber-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                <span
                  className={`text-xs ${
                    isToday ? "font-bold text-amber-500 dark:text-amber-400" : "text-slate-600 dark:text-slate-300"
                  }`}
                >
                  {d}
                </span>
                {has && v !== 0 && (
                  <span className={`mt-0.5 text-[9px] font-bold leading-none ${pnlClass(v)}`}>
                    <span className="sm:hidden">{wonCompact(v)}</span>
                    <span className="hidden sm:inline">{wonCompact(v, true)}</span>
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
        <section key={selected} className="animate-detail-in mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
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
          ) : !detail || (detail.buys.length === 0 && (detail.roundtrips?.length ?? 0) === 0) ? (
            <div className="flex min-h-[140px] items-center justify-center">
              <p className="text-sm text-slate-400">이 날의 매매 기록이 없어요.</p>
            </div>
          ) : (
            <div className="mt-3 space-y-4">
              {(detail.roundtrips?.length ?? 0) > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-slate-400">청산 (매수가 → 매도가)</p>
                  <RoundTrips trips={detail.roundtrips} names={names} plans={detail.plans} />
                </div>
              )}
              {detail.buys.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-slate-400">이 날 매수</p>
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                    {detail.buys.map((o) => (
                      <li key={o.id} className="flex items-center justify-between py-2">
                        <span className="font-medium">{nm(o.stk_cd)}</span>
                        <span className="text-sm text-slate-500 tabular-nums">{o.filled_qty || o.qty}주 · {wonExact(o.fill_price ?? o.price)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* 주간 실현손익 */}
      <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
        <h2 className="text-base font-bold">주간 실현손익</h2>
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {weeks.map((week, wi) => {
            const days = week.filter((d): d is number => d !== null);
            const weekSum = days.reduce((s, d) => s + (data?.days?.[dayKey(d)]?.realized_pnl ?? 0), 0);
            const weekHas = days.some((d) => data?.days?.[dayKey(d)]);
            const first = days[0];
            const last = days[days.length - 1];
            return (
              <li key={`w${wi}`} className="flex items-center justify-between py-2.5">
                <span className="text-sm text-slate-500">
                  {wi + 1}주차 <span className="text-slate-400">· {mo}/{first}~{mo}/{last}</span>
                </span>
                {weekHas ? (
                  <span className={`text-sm font-bold tabular-nums ${pnlClass(weekSum)}`}>{won(weekSum)}</span>
                ) : (
                  <span className="text-sm text-slate-300">·</span>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </main>
  );
}
