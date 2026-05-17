import Link from "next/link";
import { DailySummary } from "@/types";
import { ArrowUpRight, TrendingUp, TrendingDown, FileText } from "lucide-react";
import { StockPriceBadge } from "@/components/StockPriceBadge";

interface Props {
  summary: DailySummary | null;
}

const MARKET_LABEL: Record<string, string> = { US: "🇺🇸 미국장", KR: "🇰🇷 한국장" };

export function TopPicks({ summary }: Props) {
  if (!summary) {
    return (
      <section>
        <SectionHeader title="오늘의 추천" />
        <div className="rounded-3xl bg-white p-6 text-center text-sm text-slate-400 dark:bg-slate-900/60">
          오늘은 아직 리포트가 준비되지 않았어요.
        </div>
      </section>
    );
  }

  return (
    <section>
      <SectionHeader
        title="오늘의 추천"
        action={
          <Link
            href={`/reports/${summary.report_date}`}
            className="inline-flex items-center gap-1 rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-bold text-white transition-opacity hover:opacity-90 dark:bg-white dark:text-slate-900"
          >
            <FileText className="h-3.5 w-3.5" />
            리포트 보기
          </Link>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
        <PickCard
          tone="buy"
          stock={summary.buy_stock}
          ticker={summary.buy_ticker}
          reason={summary.buy_reason}
          market={summary.market}
        />
        <PickCard
          tone="sell"
          stock={summary.sell_stock}
          ticker={summary.sell_ticker}
          reason={summary.sell_reason}
          market={summary.market}
        />
      </div>
    </section>
  );
}

function PickCard({
  tone,
  stock,
  ticker,
  reason,
  market,
}: {
  tone: "buy" | "sell";
  stock: string;
  ticker?: string;
  reason: string;
  market?: "US" | "KR" | null;
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

  const Card = (
    <div
      className={`group relative h-full overflow-hidden rounded-3xl ${bg} p-5 transition-all hover:shadow-md sm:p-6`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold ${accent} dark:bg-slate-900/50`}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </span>
        {market && (
          <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400">
            {MARKET_LABEL[market]}
          </span>
        )}
      </div>

      <div className="mt-4 flex items-baseline gap-2">
        <p className="truncate text-2xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-3xl">
          {stock || "종목 없음"}
        </p>
        {ticker && <StockPriceBadge ticker={ticker} />}
      </div>

      <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {reason}
      </p>

      {ticker && (
        <div className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-slate-700 dark:text-slate-200">
          자세히 보기
          <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </div>
      )}
    </div>
  );

  return ticker ? <Link href={`/stocks/${ticker}`}>{Card}</Link> : Card;
}

function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-2">
      <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
        {title}
      </h2>
      {action}
    </div>
  );
}
