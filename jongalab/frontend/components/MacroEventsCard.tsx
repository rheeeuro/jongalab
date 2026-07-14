"use client";

import { useEffect, useState } from "react";
import type { MacroEvent, MacroEventsResponse } from "@/types";
import { CalendarClock } from "lucide-react";

const WD = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-07-30" → "7/30(목)" */
function fmtDay(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}(${WD[d.getDay()]})`;
}

/** 오늘 기준 D-day 라벨 (오늘/내일/D-n) */
function dday(date: string): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((new Date(`${date}T00:00:00`).getTime() - today.getTime()) / 86_400_000);
  if (diff <= 0) return "오늘";
  if (diff === 1) return "내일";
  return `D-${diff}`;
}

/**
 * 다가오는 거시 이벤트 카드 (마켓 페이지) — macro_event 캘린더의 향후 30일.
 * severity 3(FOMC·CPI·고용)은 전야에 자동매매 시드가 축소되는 이벤트라 주황으로 강조한다.
 */
export function MacroEventsCard() {
  const [events, setEvents] = useState<MacroEvent[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/macro-events?days=30", { cache: "no-store" });
        if (cancelled) return;
        const data: MacroEventsResponse | null = res.ok ? await res.json() : null;
        setEvents(data?.events ?? []);
      } catch {
        if (!cancelled) setEvents([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!events || events.length === 0) return null; // 로딩·실패·이벤트 없음 — 카드 자체를 숨김

  return (
    <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <h2 className="mb-1 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
        <CalendarClock className="h-5 w-5 text-amber-500" />
        다가오는 거시 이벤트
      </h2>
      <p className="mb-3 text-xs text-slate-400">
        향후 30일 · <span className="font-semibold text-amber-500">주황</span> 이벤트 전야엔 자동매매
        시드가 축소돼요
      </p>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {events.map((ev) => {
          const major = ev.severity >= 3;
          return (
            <li key={`${ev.date}${ev.time}${ev.name}`} className="flex items-center gap-3 py-2.5">
              <span
                className={`w-11 shrink-0 rounded-md px-1.5 py-0.5 text-center text-[11px] font-bold ${
                  major
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400"
                    : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                }`}
              >
                {dday(ev.date)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {ev.name}
                </p>
                <p className="text-xs text-slate-400 tabular-nums">
                  {fmtDay(ev.date)} {ev.time}
                </p>
              </div>
              {major && (
                <span className="shrink-0 text-[11px] font-medium text-amber-500">시드 축소</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
