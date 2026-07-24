import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, LineChart } from "lucide-react";
import { MarketIndexHistory } from "@/types";
import { MarketIndexChart } from "@/components/MarketIndexChart";
import { apiFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getIndexHistory(symbol: string): Promise<MarketIndexHistory> {
  // 초기 로드는 5일 분봉(프리·애프터 포함). 범위 토글은 클라이언트가 refetch.
  return apiFetch<MarketIndexHistory>(
    `/api/market-index-history/${encodeURIComponent(symbol)}?range=5d`,
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

export default async function MarketIndexDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const decoded = decodeURIComponent(symbol);
  const { name, candles } = await getIndexHistory(decoded);

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
        </header>

        <section className="rounded-3xl bg-white p-4 dark:bg-slate-900/60 sm:p-6">
          <MarketIndexChart symbol={decoded} initialCandles={candles} />
        </section>
      </div>
    </main>
  );
}
