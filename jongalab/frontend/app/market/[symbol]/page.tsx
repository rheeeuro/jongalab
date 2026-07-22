import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, LineChart, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { MarketIndexHistory } from "@/types";
import { CandlestickChart } from "@/components/CandlestickChart";
import { apiFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getIndexHistory(symbol: string): Promise<MarketIndexHistory> {
  return apiFetch<MarketIndexHistory>(
    `/api/market-index-history/${encodeURIComponent(symbol)}`,
    { symbol, name: symbol, candles: [] },
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>;
}): Promise<Metadata> {
  const { symbol } = await params;
  const decoded = decodeURIComponent(symbol);
  const { name } = await getIndexHistory(decoded);
  return {
    title: `${name} — 시장 차트`,
    alternates: { canonical: `/market/${encodeURIComponent(decoded)}` },
  };
}

function formatPrice(price: number, symbol: string): string {
  if (symbol === "USDKRW=X") {
    return `₩${price.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (symbol === "BTC-USD") {
    return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default async function MarketIndexDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const decoded = decodeURIComponent(symbol);
  const { name, candles } = await getIndexHistory(decoded);

  const last = candles.at(-1);
  const prev = candles.at(-2);
  const change = last && prev ? last.close - prev.close : null;
  const pct = change !== null && prev ? (change / prev.close) * 100 : null;

  const isUp = (pct ?? 0) > 0;
  const isDown = (pct ?? 0) < 0;
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500 dark:text-slate-400";

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
        <Link
          href="/market"
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          시장으로
        </Link>

        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <LineChart className="h-4 w-4 text-indigo-500" />
            <span>시장 상세 차트</span>
          </div>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="text-2xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-3xl">
              {name}
            </h1>
            <span className="text-sm font-bold text-slate-400 dark:text-slate-500">{decoded}</span>
          </div>
          {last && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-2xl font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100">
                {formatPrice(last.close, decoded)}
              </span>
              {change !== null && pct !== null && (
                <span className={`flex items-center gap-1 text-sm font-bold tabular-nums ${changeColor}`}>
                  <Icon className="h-4 w-4" />
                  {isUp ? "+" : ""}
                  {change.toFixed(2)} ({isUp ? "+" : ""}
                  {pct.toFixed(2)}%)
                </span>
              )}
            </div>
          )}
        </header>

        <section className="rounded-3xl bg-white p-4 dark:bg-slate-900/60 sm:p-6">
          {candles.length > 0 ? (
            <CandlestickChart data={candles} initialRangeDays={120} />
          ) : (
            <p className="py-12 text-center text-sm text-slate-400">
              이 지표는 차트 데이터를 제공하지 않습니다.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
