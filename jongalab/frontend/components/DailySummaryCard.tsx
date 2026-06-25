import { StockReport } from "@/types";
import { TrendingUp, Calendar, ArrowRight, FileText, Trophy } from "lucide-react";
import { StockPriceBadge } from "./StockPriceBadge";
import Link from "next/link";

interface Props {
  pick: StockReport | null;
  disableLink?: boolean;
}

export function DailySummaryCard({ pick, disableLink }: Props) {
  if (!pick) return null;

  const reportHref = `/reports/${pick.report_date}`;

  return (
    <div className="overflow-hidden rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-7">
      {/* 헤더 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
            🤖 오늘의 추천 종목
          </h2>
        </div>

        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            <Calendar className="h-3 w-3" />
            {pick.report_date}
          </span>
          {!disableLink && (
            <Link
              href={reportHref}
              className="group inline-flex shrink-0 items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-xs font-extrabold text-white transition-opacity hover:opacity-90 dark:bg-white dark:text-slate-900 sm:text-sm"
            >
              <FileText className="h-3.5 w-3.5" />
              리포트 보기
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          )}
        </div>
      </div>

      <div className="mt-5 rounded-2xl bg-gradient-to-br from-rose-50 to-orange-50 p-4 dark:from-rose-950/40 dark:to-orange-950/30 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold text-rose-600 dark:bg-slate-900/50 dark:text-rose-400">
            <TrendingUp className="h-3.5 w-3.5" />
            강력 매수
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-extrabold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
            <Trophy className="h-3.5 w-3.5" />
            종목 랭킹 1위
          </span>
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold text-slate-700 tabular-nums dark:bg-slate-900/50 dark:text-slate-200">
            종합 {Math.round(pick.score)}점
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-baseline gap-2">
          {pick.stock_code ? (
            <Link
              href={`/stocks/${pick.stock_code}`}
              className="text-xl font-extrabold tracking-tight text-slate-900 transition-colors hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-400 sm:text-2xl"
            >
              {pick.stock_name || "종목 없음"}
            </Link>
          ) : (
            <span className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
              {pick.stock_name || "종목 없음"}
            </span>
          )}
          {pick.stock_code && (
            <StockPriceBadge ticker={pick.stock_code} date={pick.report_date} />
          )}
        </div>

        <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {pick.reason}
        </p>
      </div>
    </div>
  );
}
