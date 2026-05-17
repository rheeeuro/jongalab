import Link from "next/link";
import { DailySummary } from "@/types";
import { ChevronRight, FileText } from "lucide-react";

interface Props {
  reports: DailySummary[];
}

const MARKET_PILL: Record<string, string> = {
  US: "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
  KR: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

export function RecentReportsRow({ reports }: Props) {
  if (!reports.length) return null;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          <FileText className="h-5 w-5 text-indigo-500" />
          지난 리포트
        </h2>
        <Link
          href="/reports"
          className="inline-flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          아카이브
          <ChevronRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2.5 pb-1 sm:grid sm:grid-cols-2 sm:gap-3 lg:grid-cols-5">
          {reports.map((r) => (
            <Link key={r.id} href={`/reports/${r.report_date}`} className="block">
              <div className="group relative h-full min-w-[170px] overflow-hidden rounded-2xl bg-white p-4 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60 sm:min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-400 dark:text-slate-500">
                    {r.report_date}
                  </span>
                  {r.market && (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[9px] font-extrabold ${
                        MARKET_PILL[r.market] ||
                        "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                      }`}
                    >
                      {r.market}
                    </span>
                  )}
                </div>
                <p className="mt-2 line-clamp-2 text-sm font-extrabold text-slate-900 dark:text-slate-100">
                  {r.buy_stock || "추천 종목"}
                </p>
                <ChevronRight className="absolute bottom-3 right-3 h-4 w-4 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-slate-600" />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
