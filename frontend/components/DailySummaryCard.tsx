import { DailySummary } from "@/types";
import { TrendingUp, TrendingDown, Calendar, ArrowRight, FileText } from "lucide-react";
import { StockPriceBadge } from "./StockPriceBadge";
import Link from "next/link";

interface Props {
  summary: DailySummary | null;
  disableLink?: boolean;
}

const MARKET_LABEL: Record<string, string> = { US: "🇺🇸 미국장", KR: "🇰🇷 한국장" };
const MARKET_STYLE: Record<string, string> = {
  US: "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
  KR: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

export function DailySummaryCard({ summary, disableLink }: Props) {
  if (!summary) return null;

  const reportHref = `/reports/${summary.report_date}`;

  return (
    <div className="overflow-hidden rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-7">
      {/* 헤더 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
            🤖 오늘의 AI 투자 전략
          </h2>
          {summary.market && (
            <span
              className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-extrabold ${MARKET_STYLE[summary.market] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"}`}
            >
              {MARKET_LABEL[summary.market] || summary.market}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            <Calendar className="h-3 w-3" />
            {summary.report_date}
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

      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-4">
        <PickBlock
          tone="buy"
          stock={summary.buy_stock}
          ticker={summary.buy_ticker}
          reason={summary.buy_reason}
          date={summary.report_date}
        />
        <PickBlock
          tone="sell"
          stock={summary.sell_stock}
          ticker={summary.sell_ticker}
          reason={summary.sell_reason}
          date={summary.report_date}
        />
      </div>
    </div>
  );
}

function PickBlock({
  tone,
  stock,
  ticker,
  reason,
  date,
}: {
  tone: "buy" | "sell";
  stock: string;
  ticker?: string;
  reason: string;
  date?: string;
}) {
  const isBuy = tone === "buy";
  const bg = isBuy
    ? "bg-gradient-to-br from-rose-50 to-orange-50 dark:from-rose-950/40 dark:to-orange-950/30"
    : "bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/30";
  const accent = isBuy
    ? "text-rose-600 dark:text-rose-400"
    : "text-blue-600 dark:text-blue-400";
  const Icon = isBuy ? TrendingUp : TrendingDown;
  const label = isBuy ? "강력 매수" : "매도/관망";

  return (
    <div className={`rounded-2xl ${bg} p-4 sm:p-5`}>
      <div
        className={`inline-flex items-center gap-1.5 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold ${accent} dark:bg-slate-900/50`}
      >
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-2">
        {ticker ? (
          <Link
            href={`/stocks/${ticker}`}
            className="text-xl font-extrabold tracking-tight text-slate-900 transition-colors hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-400 sm:text-2xl"
          >
            {stock || "종목 없음"}
          </Link>
        ) : (
          <span className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
            {stock || "종목 없음"}
          </span>
        )}
        {ticker && <StockPriceBadge ticker={ticker} date={date} />}
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {reason}
      </p>
    </div>
  );
}
