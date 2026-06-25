"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChevronRight } from "lucide-react";

export type CalendarGap = { wins: number; losses: number; total: number };

export type CalendarCellData = {
  day: number;
  dateStr: string;
  isToday: boolean;
  buyStock: string;
  themes: string[];
  gap: CalendarGap | null;
} | null;

const WEEKDAYS = ["월", "화", "수", "목", "금"];

export function ReportCalendarGrid({
  weeks,
}: {
  weeks: CalendarCellData[][];
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);

  const selectedCell =
    selected !== null
      ? weeks.flat().find((c) => c && c.dateStr === selected) ?? null
      : null;

  function handleClick(cell: NonNullable<CalendarCellData>) {
    // 데스크탑은 바로 이동, 모바일은 아래 상세 토글
    if (typeof window !== "undefined" && window.innerWidth >= 640) {
      router.push(`/reports/${cell.dateStr}`);
      return;
    }
    setSelected((prev) => (prev === cell.dateStr ? null : cell.dateStr));
  }

  return (
    <div>
      {/* 요일 헤더 */}
      <div className="mb-1.5 grid grid-cols-5 gap-1.5 sm:gap-2">
        {WEEKDAYS.map((w) => (
          <div
            key={w}
            className="text-center text-[11px] font-extrabold text-slate-400 dark:text-slate-500"
          >
            {w}
          </div>
        ))}
      </div>

      {/* 주 단위 그리드 */}
      <div className="space-y-1.5 sm:space-y-2">
        {weeks.map((week, wi) => (
          <div key={wi} className="grid grid-cols-5 gap-1.5 sm:gap-2">
            {week.map((cell, ci) => (
              <Cell
                key={ci}
                cell={cell}
                selected={!!cell && cell.dateStr === selected}
                onSelect={handleClick}
              />
            ))}
          </div>
        ))}
      </div>

      {/* 모바일 전용 상세 패널 */}
      {selectedCell && (
        <Link
          href={`/reports/${selectedCell.dateStr}`}
          className="mt-3 block rounded-2xl bg-white p-4 shadow-sm dark:bg-slate-900/60 sm:hidden"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-black text-slate-900 dark:text-slate-100">
              {selectedCell.dateStr}
            </span>
            {selectedCell.gap && selectedCell.gap.total > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-extrabold tabular-nums text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                🌅 {selectedCell.gap.wins}승 {selectedCell.gap.losses}패
              </span>
            )}
          </div>

          <div className="mt-3 space-y-1.5">
            {selectedCell.buyStock && (
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-extrabold text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
                  매수
                </span>
                <span className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
                  {selectedCell.buyStock}
                </span>
              </div>
            )}
          </div>

          {selectedCell.themes.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {selectedCell.themes.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          <div className="mt-3 flex items-center justify-end text-xs font-bold text-indigo-600 dark:text-indigo-400">
            전체 리포트 보기
            <ChevronRight className="h-3.5 w-3.5" />
          </div>
        </Link>
      )}
    </div>
  );
}

function DayBadge({
  day,
  isToday,
  center,
}: {
  day: number;
  isToday: boolean;
  center?: boolean;
}) {
  if (isToday) {
    return (
      <span
        className={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-indigo-600 px-1 text-xs font-extrabold text-white ${
          center ? "" : ""
        }`}
      >
        {day}
      </span>
    );
  }
  return (
    <span className="text-xs font-extrabold text-slate-900 dark:text-slate-100">
      {day}
    </span>
  );
}

function Cell({
  cell,
  selected,
  onSelect,
}: {
  cell: CalendarCellData;
  selected: boolean;
  onSelect: (cell: NonNullable<CalendarCellData>) => void;
}) {
  if (!cell) {
    return <div className="min-h-[44px] sm:min-h-[132px]" />;
  }

  const hasReport = !!(cell.buyStock || cell.themes.length);

  // 리포트 없는 평일
  if (!hasReport) {
    return (
      <div
        className={`flex min-h-[44px] items-center justify-center rounded-lg border border-dashed p-1 sm:min-h-[132px] sm:items-start sm:justify-start sm:rounded-xl sm:p-2 ${
          cell.isToday
            ? "border-indigo-300 dark:border-indigo-700"
            : "border-slate-200 dark:border-slate-800"
        }`}
      >
        {cell.isToday ? (
          <DayBadge day={cell.day} isToday />
        ) : (
          <span className="text-xs font-bold text-slate-300 dark:text-slate-600">
            {cell.day}
          </span>
        )}
      </div>
    );
  }

  const hasGap = cell.gap && cell.gap.total > 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(cell)}
      className={`flex min-h-[44px] flex-col rounded-lg bg-white p-1 text-left transition-all hover:shadow-md dark:bg-slate-900/60 sm:min-h-[132px] sm:gap-1 sm:p-2 sm:hover:-translate-y-0.5 ${
        cell.isToday || selected ? "ring-2 ring-indigo-500" : ""
      }`}
    >
      {/* 모바일: 날짜 + 점만 */}
      <span className="flex h-full w-full flex-col items-center justify-center gap-1 sm:hidden">
        <DayBadge day={cell.day} isToday={cell.isToday} center />
        <span className="h-1 w-1 rounded-full bg-indigo-500" />
      </span>

      {/* 데스크탑: 전체 내용 */}
      <span className="hidden w-full flex-col gap-1 sm:flex">
        <span className="flex items-center justify-between">
          <DayBadge day={cell.day} isToday={cell.isToday} />
          {hasGap && (
            <span className="whitespace-nowrap rounded-full bg-amber-100 px-1 py-px text-[9px] font-extrabold tabular-nums text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              🌅 {cell.gap!.wins}승 {cell.gap!.losses}패
            </span>
          )}
        </span>

        <span className="flex flex-col gap-0.5">
          {cell.buyStock && (
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
              <span className="min-w-0 truncate text-[11px] font-extrabold text-slate-900 dark:text-slate-100">
                {cell.buyStock}
              </span>
            </span>
          )}
        </span>

        <span className="mt-auto flex flex-col gap-0.5">
          {cell.themes.map((t) => (
            <span
              key={t}
              className="truncate rounded bg-violet-100 px-1 py-px text-[10px] font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
            >
              {t}
            </span>
          ))}
        </span>
      </span>
    </button>
  );
}
