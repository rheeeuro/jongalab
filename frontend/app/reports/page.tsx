import { DailySummary } from "@/types";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { FileText, ChevronRight, Calendar } from "lucide-react";

type GapStat = { wins: number; losses: number; flats: number; total: number };

async function getDailySummaryList(market: string): Promise<DailySummary[]> {
  return apiFetch(`/api/daily-summary-list?limit=100&market=${market}`, []);
}

async function getGapStats(dates: string[]): Promise<Record<string, GapStat>> {
  if (dates.length === 0) return {};
  return apiFetch(
    `/api/stock-report/gap-stats?dates=${encodeURIComponent(dates.join(","))}`,
    {},
  );
}

export const dynamic = "force-dynamic";

const MARKET_PILL: Record<string, string> = {
  US: "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
  KR: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

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

export default async function ReportsArchivePage(props: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await props.searchParams;
  const market = (params?.market as string) || "ALL";
  const reports = await getDailySummaryList(market);
  const gapStats = await getGapStats(reports.map((r) => r.report_date));
  const grouped = groupByMonth(reports);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
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
            {grouped.map(([month, monthReports]) => (
              <section key={month}>
                <h2 className="mb-4 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-xl">
                  <Calendar className="h-5 w-5 text-indigo-500" />
                  {formatMonth(month)}
                  <span className="text-xs font-bold text-slate-400">
                    {monthReports.length}건
                  </span>
                </h2>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {monthReports.map((r) => {
                    const gap = gapStats[r.report_date];
                    const winRate =
                      gap && gap.total > 0
                        ? (gap.wins / gap.total) * 100
                        : null;
                    return (
                    <Link
                      key={r.id}
                      href={`/reports/${r.report_date}`}
                      className="group block overflow-hidden rounded-2xl bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-extrabold text-slate-500 dark:text-slate-400">
                          {r.report_date}
                        </span>
                        {r.market && (
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
                              MARKET_PILL[r.market] ||
                              "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                            }`}
                          >
                            {r.market}
                          </span>
                        )}
                      </div>
                      <div className="mt-3 space-y-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[9px] font-extrabold text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
                            매수
                          </span>
                          <span className="truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
                            {r.buy_stock || "-"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[9px] font-extrabold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
                            매도
                          </span>
                          <span className="truncate text-sm font-bold text-slate-600 dark:text-slate-300">
                            {r.sell_stock || "-"}
                          </span>
                        </div>
                      </div>
                      {gap && gap.total > 0 && (
                        <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                          <span>🌅 갭</span>
                          <span className="text-rose-600 dark:text-rose-400">
                            {gap.wins}승
                          </span>
                          <span className="text-blue-600 dark:text-blue-400">
                            {gap.losses}패
                          </span>
                          {winRate !== null && (
                            <span className="ml-auto tabular-nums">
                              {winRate.toFixed(0)}%
                            </span>
                          )}
                        </div>
                      )}
                      <div className="mt-3 flex items-center justify-end text-xs font-bold text-slate-400 group-hover:text-slate-900 dark:group-hover:text-slate-100">
                        자세히
                        <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                      </div>
                    </Link>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
