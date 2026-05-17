import { StockReport } from "@/types";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Crown,
  FileBarChart,
} from "lucide-react";

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white",
  D: "bg-slate-300 text-white",
};

export function StockReportHistory({ reports }: { reports: StockReport[] }) {
  if (reports.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileBarChart className="h-5 w-5 text-indigo-500" />
        <h2 className="text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-xl">
          최근 일간 리포트
        </h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {reports.length}일
        </span>
      </div>

      <div className="space-y-2">
        {reports.map((r) => {
          const isUp = r.change_pct > 0;
          const isDown = r.change_pct < 0;
          const ChangeIcon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;

          return (
            <Link
              key={r.report_date}
              href={`/reports/${r.report_date}/${r.stock_code}`}
              className="group block rounded-2xl bg-white p-4 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60"
            >
              <div className="flex items-center gap-3">
                {/* 날짜 */}
                <div className="shrink-0">
                  <span className="text-xs font-extrabold text-slate-500 dark:text-slate-400">
                    {r.report_date}
                  </span>
                </div>

                {/* 종목명 & 섹터 */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-400">
                      {r.stock_name}
                    </span>
                    {r.is_leader && (
                      <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                    )}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {r.sector} · #{r.rank_no} ·{" "}
                    {(r.trading_value / 1e8).toLocaleString("ko-KR", {
                      maximumFractionDigits: 0,
                    })}억
                  </div>
                </div>

                {/* 수급 */}
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
                    GRADE_TONE[r.supply_grade] || GRADE_TONE.D
                  }`}
                >
                  수급{r.supply_grade}
                </span>

                {/* 등락 */}
                <div className="flex w-16 shrink-0 items-center justify-end gap-1">
                  <ChangeIcon
                    className={`h-3.5 w-3.5 ${
                      isUp
                        ? "text-rose-500"
                        : isDown
                          ? "text-blue-500"
                          : "text-slate-400"
                    }`}
                  />
                  <span
                    className={`text-sm font-extrabold tabular-nums ${
                      isUp
                        ? "text-rose-600 dark:text-rose-400"
                        : isDown
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-slate-500"
                    }`}
                  >
                    {isUp ? "+" : ""}
                    {r.change_pct.toFixed(1)}%
                  </span>
                </div>

                {/* 점수 */}
                <div className="w-14 shrink-0 text-right tabular-nums">
                  <span className="text-base font-extrabold text-indigo-600 dark:text-indigo-400">
                    {r.score.toFixed(0)}
                  </span>
                  <span className="text-xs text-slate-400">점</span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
