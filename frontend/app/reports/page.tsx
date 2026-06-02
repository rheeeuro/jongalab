import { DailySummary } from "@/types";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { FileText, Calendar } from "lucide-react";

type GapStat = { wins: number; losses: number; flats: number; total: number };

async function getDailySummaryList(): Promise<DailySummary[]> {
  return apiFetch(`/api/daily-summary-list?limit=100`, []);
}

async function getGapStats(dates: string[]): Promise<Record<string, GapStat>> {
  if (dates.length === 0) return {};
  return apiFetch(
    `/api/stock-report/gap-stats?dates=${encodeURIComponent(dates.join(","))}`,
    {},
  );
}

async function getTopThemes(
  dates: string[],
): Promise<Record<string, string[]>> {
  if (dates.length === 0) return {};
  return apiFetch(
    `/api/sector-report/top-themes?dates=${encodeURIComponent(dates.join(","))}&limit=3`,
    {},
  );
}

export const dynamic = "force-dynamic";

const WEEKDAYS = ["월", "화", "수", "목", "금"];

function groupByMonth(reports: DailySummary[]) {
  const groups = new Map<string, DailySummary[]>();
  for (const r of reports) {
    const month = r.report_date.slice(0, 7); // YYYY-MM
    if (!groups.has(month)) groups.set(month, []);
    groups.get(month)!.push(r);
  }
  return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
}

function formatMonth(monthStr: string): string {
  const [y, m] = monthStr.split("-");
  return `${y}년 ${parseInt(m, 10)}월`;
}

type DayCell = { day: number; dateStr: string; report: DailySummary | null } | null;

// 월~금 기준으로 한 달을 주 단위 그리드로 분해한다 (주말 제외).
function buildWeeks(
  monthStr: string,
  reportsByDate: Map<string, DailySummary>,
): DayCell[][] {
  const [y, m] = monthStr.split("-").map(Number);
  const daysInMonth = new Date(y, m, 0).getDate();
  const weeks: DayCell[][] = [];
  let week: DayCell[] = [null, null, null, null, null];
  let hasEntry = false;

  for (let d = 1; d <= daysInMonth; d++) {
    const dow = new Date(y, m - 1, d).getDay(); // 0=일 ... 6=토
    if (dow === 0 || dow === 6) continue; // 주말 제외
    const col = dow - 1; // 월=0 ... 금=4
    if (col === 0 && hasEntry) {
      weeks.push(week);
      week = [null, null, null, null, null];
      hasEntry = false;
    }
    const dateStr = `${monthStr}-${String(d).padStart(2, "0")}`;
    week[col] = { day: d, dateStr, report: reportsByDate.get(dateStr) ?? null };
    hasEntry = true;
  }
  if (hasEntry) weeks.push(week);
  return weeks;
}

export default async function ReportsArchivePage() {
  const reports = await getDailySummaryList();
  const dates = reports.map((r) => r.report_date);
  const [gapStats, topThemes] = await Promise.all([
    getGapStats(dates),
    getTopThemes(dates),
  ]);
  const grouped = groupByMonth(reports);

  const reportsByDate = new Map<string, DailySummary>();
  for (const r of reports) reportsByDate.set(r.report_date, r);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <FileText className="h-4 w-4 text-indigo-500" />
            <span>리포트 아카이브</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            지난 AI 리포트
            <br />
            다시 보기.
          </h1>
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
            지금까지 발행된 {reports.length}건의 일일 투자 리포트.
          </p>
        </header>

        {grouped.length === 0 ? (
          <div className="rounded-3xl bg-white p-12 text-center dark:bg-slate-900/60">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              아직 리포트가 없습니다.
            </p>
          </div>
        ) : (
          <div className="space-y-10">
            {grouped.map(([month, monthReports]) => {
              const weeks = buildWeeks(month, reportsByDate);
              return (
                <section key={month}>
                  <h2 className="mb-4 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-xl">
                    <Calendar className="h-5 w-5 text-indigo-500" />
                    {formatMonth(month)}
                    <span className="text-xs font-bold text-slate-400">
                      {monthReports.length}건
                    </span>
                  </h2>

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
                      <div
                        key={wi}
                        className="grid grid-cols-5 gap-1.5 sm:gap-2"
                      >
                        {week.map((cell, ci) => (
                          <CalendarCell
                            key={ci}
                            cell={cell}
                            gap={cell ? gapStats[cell.dateStr] : undefined}
                            themes={cell ? topThemes[cell.dateStr] : undefined}
                          />
                        ))}
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}

function CalendarCell({
  cell,
  gap,
  themes,
}: {
  cell: DayCell;
  gap?: GapStat;
  themes?: string[];
}) {
  if (!cell) {
    return <div className="min-h-[96px] sm:min-h-[132px]" />;
  }

  // 리포트가 없는 평일
  if (!cell.report) {
    return (
      <div className="flex min-h-[96px] flex-col rounded-xl border border-dashed border-slate-200 p-2 dark:border-slate-800 sm:min-h-[132px]">
        <span className="text-xs font-bold text-slate-300 dark:text-slate-600">
          {cell.day}
        </span>
      </div>
    );
  }

  const topThemes = themes?.slice(0, 3) ?? [];
  const hasGap = gap && gap.total > 0;
  const r = cell.report;

  return (
    <Link
      href={`/reports/${cell.dateStr}`}
      className="group flex min-h-[96px] flex-col gap-1 rounded-xl bg-white p-2 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60 sm:min-h-[132px]"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-extrabold text-slate-900 dark:text-slate-100">
          {cell.day}
        </span>
        {hasGap && (
          <span className="rounded-full bg-amber-100 px-1 py-px text-[9px] font-extrabold tabular-nums text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
            🌅 {gap!.wins}승 {gap!.losses}패
          </span>
        )}
      </div>

      {/* 오늘의 종목 */}
      <div className="space-y-0.5">
        {r.buy_stock && (
          <div className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
            <span className="truncate text-[11px] font-extrabold text-slate-900 dark:text-slate-100">
              {r.buy_stock}
            </span>
          </div>
        )}
        {r.sell_stock && (
          <div className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
            <span className="truncate text-[11px] font-bold text-slate-500 dark:text-slate-400">
              {r.sell_stock}
            </span>
          </div>
        )}
      </div>

      <div className="mt-auto flex flex-wrap gap-0.5">
        {topThemes.map((t) => (
          <span
            key={t}
            className="truncate rounded bg-violet-100 px-1 py-px text-[10px] font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
          >
            {t}
          </span>
        ))}
      </div>
    </Link>
  );
}
