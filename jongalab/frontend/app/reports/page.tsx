import { TopPick } from "@/types";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { FileText, ChevronLeft, ChevronRight } from "lucide-react";
import {
  ReportCalendarGrid,
  CalendarCellData,
} from "@/components/ReportCalendarGrid";

type GapStat = { wins: number; losses: number; flats: number; total: number };

async function getReportDates(): Promise<string[]> {
  return apiFetch(`/api/stock-report/dates?limit=100`, []);
}

async function getTopPicks(dates: string[]): Promise<Record<string, TopPick>> {
  if (dates.length === 0) return {};
  return apiFetch(
    `/api/stock-report/top-picks?dates=${encodeURIComponent(dates.join(","))}`,
    {},
  );
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

function formatMonth(monthStr: string): string {
  const [y, m] = monthStr.split("-");
  return `${y}년 ${parseInt(m, 10)}월`;
}

// 한국 시간 기준 오늘 날짜 (YYYY-MM-DD)
function todayInSeoul(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" });
}

// monthStr(YYYY-MM)을 delta 개월 이동
function shiftMonth(monthStr: string, delta: number): string {
  const [y, m] = monthStr.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type DayCell = { day: number; dateStr: string; pick: TopPick | null } | null;

// 월~금 기준으로 한 달을 주 단위 그리드로 분해한다 (주말 제외).
function buildWeeks(
  monthStr: string,
  picksByDate: Map<string, TopPick>,
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
    week[col] = { day: d, dateStr, pick: picksByDate.get(dateStr) ?? null };
    hasEntry = true;
  }
  if (hasEntry) weeks.push(week);
  return weeks;
}

export default async function ReportsArchivePage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const sp = await searchParams;
  const dates = await getReportDates();
  const [gapStats, topThemes, picks] = await Promise.all([
    getGapStats(dates),
    getTopThemes(dates),
    getTopPicks(dates),
  ]);

  const picksByDate = new Map<string, TopPick>();
  for (const [date, pick] of Object.entries(picks)) picksByDate.set(date, pick);

  const todayStr = todayInSeoul();
  const todayMonth = todayStr.slice(0, 7);

  // 데이터가 있는 월 범위 + 오늘이 속한 월을 탐색 경계로 삼는다
  const monthsWithData = Array.from(
    new Set(dates.map((d) => d.slice(0, 7))),
  ).sort();
  const minMonth = monthsWithData[0] ?? todayMonth;
  const maxData = monthsWithData[monthsWithData.length - 1] ?? todayMonth;
  const maxMonth = maxData > todayMonth ? maxData : todayMonth;

  // 선택된 월 (기본: 오늘이 속한 월), 경계 밖이면 클램프
  let selectedMonth =
    sp.month && /^\d{4}-\d{2}$/.test(sp.month) ? sp.month : todayMonth;
  if (selectedMonth < minMonth) selectedMonth = minMonth;
  if (selectedMonth > maxMonth) selectedMonth = maxMonth;

  const prevMonth = shiftMonth(selectedMonth, -1);
  const nextMonth = shiftMonth(selectedMonth, 1);
  const canPrev = selectedMonth > minMonth;
  const canNext = selectedMonth < maxMonth;

  const weeks = buildWeeks(selectedMonth, picksByDate);

  // 클라이언트 컴포넌트로 넘길 직렬화 가능한 셀 데이터
  const cellWeeks: CalendarCellData[][] = weeks.map((week) =>
    week.map((cell) => {
      if (!cell) return null;
      const gap = gapStats[cell.dateStr];
      return {
        day: cell.day,
        dateStr: cell.dateStr,
        isToday: cell.dateStr === todayStr,
        buyStock: cell.pick?.stock_name ?? "",
        themes: (topThemes[cell.dateStr] ?? []).slice(0, 3),
        gap:
          gap && gap.total > 0
            ? { wins: gap.wins, losses: gap.losses, total: gap.total }
            : null,
      };
    }),
  );

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
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
            날짜를 선택해 그날의 AI 투자 리포트를 확인하세요.
          </p>
        </header>

        <section>
          {/* 월 이동 네비게이션 */}
          <div className="mb-4 flex items-center justify-between">
            <MonthNavButton
              month={prevMonth}
              disabled={!canPrev}
              label="이전 달"
            >
              <ChevronLeft className="h-5 w-5" />
            </MonthNavButton>

            <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
              {formatMonth(selectedMonth)}
            </h2>

            <MonthNavButton
              month={nextMonth}
              disabled={!canNext}
              label="다음 달"
            >
              <ChevronRight className="h-5 w-5" />
            </MonthNavButton>
          </div>

          {/* 캘린더 (모바일: 날짜만 → 탭하면 아래 상세, 데스크탑: 전체 내용) */}
          {cellWeeks.length === 0 ? (
            <div className="rounded-3xl bg-white p-12 text-center dark:bg-slate-900/60">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                이 달의 리포트가 없습니다.
              </p>
            </div>
          ) : (
            <ReportCalendarGrid weeks={cellWeeks} />
          )}
        </section>
      </div>
    </main>
  );
}

function MonthNavButton({
  month,
  disabled,
  label,
  children,
}: {
  month: string;
  disabled: boolean;
  label: string;
  children: React.ReactNode;
}) {
  if (disabled) {
    return (
      <span
        aria-label={label}
        className="inline-flex h-10 w-10 items-center justify-center rounded-full text-slate-200 dark:text-slate-700"
      >
        {children}
      </span>
    );
  }
  return (
    <Link
      href={`/reports?month=${month}`}
      aria-label={label}
      className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-white text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
    >
      {children}
    </Link>
  );
}

