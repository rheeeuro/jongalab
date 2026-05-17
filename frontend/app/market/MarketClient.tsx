"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import type { MarketIndex, StockReport } from "@/types";
import { MarketIndicesSection } from "@/components/MarketIndicesSection";
import { Crown, TrendingUp, TrendingDown, LineChart } from "lucide-react";

async function clientFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) return fallback;
    return res.json();
  } catch (error) {
    console.error(`API fetch error (${path}):`, error);
    return fallback;
  }
}

async function getLatestStockReports(): Promise<{
  date: string;
  reports: StockReport[];
}> {
  const dates = await clientFetch<string[]>(
    "/api/stock-report/dates?limit=1",
    [],
  );
  if (dates.length === 0) return { date: "", reports: [] };
  const reports = await clientFetch<StockReport[]>(
    `/api/stock-report/${dates[0]}`,
    [],
  );
  return { date: dates[0], reports };
}

export function MarketClient() {
  const searchParams = useSearchParams();
  const currentMarket = searchParams.get("market") || "ALL";
  const showUS = currentMarket === "ALL" || currentMarket === "US";
  const showKR = currentMarket === "ALL" || currentMarket === "KR";

  const [usLeaders, setUsLeaders] = useState<MarketIndex[]>([]);
  const [krLeaders, setKrLeaders] = useState<MarketIndex[]>([]);
  const [latestReports, setLatestReports] = useState<{
    date: string;
    reports: StockReport[];
  }>({
    date: "",
    reports: [],
  });
  const [leadersLoading, setLeadersLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadMarketData() {
      setLeadersLoading(true);

      const [nextUsLeaders, nextKrLeaders, nextLatestReports] =
        await Promise.all([
          showUS
            ? clientFetch<MarketIndex[]>("/api/market-leaders/US", [])
            : Promise.resolve([]),
          showKR
            ? clientFetch<MarketIndex[]>("/api/market-leaders/KR", [])
            : Promise.resolve([]),
          showKR
            ? getLatestStockReports()
            : Promise.resolve({ date: "", reports: [] }),
        ]);

      if (cancelled) return;
      setUsLeaders(nextUsLeaders);
      setKrLeaders(nextKrLeaders);
      setLatestReports(nextLatestReports);
      setLeadersLoading(false);
    }

    loadMarketData();

    return () => {
      cancelled = true;
    };
  }, [showUS, showKR]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        {/* 헤더 */}
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <LineChart className="h-4 w-4 text-indigo-500" />
            <span>실시간 시장</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            지금 이 순간의
            <br />
            시장 흐름.
          </h1>
        </div>

        <MarketIndicesSection showUS={showUS} showKR={showKR} />

        <div className={`grid gap-4 ${showUS && showKR ? "lg:grid-cols-2" : ""}`}>
          {showUS && (
            <LeaderPanel
              title="미국 주도주"
              accent="text-blue-500"
              icon={<TrendingUp className="h-5 w-5" />}
            >
              <LeaderList items={usLeaders} loading={leadersLoading} />
            </LeaderPanel>
          )}

          {showKR && (
            <LeaderPanel
              title="한국 주도주"
              accent="text-rose-500"
              icon={<TrendingUp className="h-5 w-5" />}
            >
              {latestReports.reports.length > 0 ? (
                <div className="space-y-2">
                  {latestReports.reports.slice(0, 10).map((r) => (
                    <StockReportRow
                      key={r.stock_code}
                      report={r}
                      date={latestReports.date}
                    />
                  ))}
                </div>
              ) : (
                <LeaderList items={krLeaders} loading={leadersLoading} />
              )}
            </LeaderPanel>
          )}
        </div>
      </div>
    </main>
  );
}

function LeaderPanel({
  title,
  accent,
  icon,
  children,
}: {
  title: string;
  accent: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
        <span className={accent}>{icon}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function LeaderList({
  items,
  loading,
}: {
  items: MarketIndex[];
  loading: boolean;
}) {
  if (loading) {
    return <p className="text-sm text-slate-400">주도주 데이터를 조회 중입니다.</p>;
  }
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">표시할 주도주 데이터가 없습니다.</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <LeaderRow key={item.symbol} item={item} />
      ))}
    </div>
  );
}

function LeaderRow({ item }: { item: MarketIndex }) {
  if (item.price === null) return null;

  const isUp = (item.change_percent ?? 0) > 0;
  const isDown = (item.change_percent ?? 0) < 0;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;

  const isKr = item.symbol.endsWith(".KS") || item.symbol.endsWith(".KQ");
  const priceStr = isKr
    ? `₩${item.price.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}`
    : `$${item.price.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

  return (
    <Link
      href={`/stocks/${item.symbol}`}
      className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 transition-all hover:-translate-y-0.5 dark:bg-slate-800/40"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate font-extrabold text-slate-900 dark:text-slate-100">
          {item.name}
        </span>
        <span className="shrink-0 text-xs text-slate-400">{item.symbol}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-sm font-bold tabular-nums text-slate-700 dark:text-slate-300">
          {priceStr}
        </span>
        <span
          className={`flex items-center gap-1 text-sm font-extrabold tabular-nums ${changeColor}`}
        >
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {isUp ? "+" : ""}
          {item.change_percent?.toFixed(2)}%
        </span>
      </div>
    </Link>
  );
}

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white",
  D: "bg-slate-300 text-white",
};

function StockReportRow({
  report: r,
  date,
}: {
  report: StockReport;
  date: string;
}) {
  const isUp = r.change_pct > 0;
  const isDown = r.change_pct < 0;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;

  return (
    <Link
      href={`/reports/${date}/${r.stock_code}`}
      className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 transition-all hover:-translate-y-0.5 dark:bg-slate-800/40"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="w-5 shrink-0 text-center text-xs font-extrabold text-indigo-500">
          {r.rank_no}
        </span>
        <span className="truncate font-extrabold text-slate-900 dark:text-slate-100">
          {r.stock_name}
        </span>
        {r.is_leader && (
          <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
        )}
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
            GRADE_TONE[r.supply_grade] || GRADE_TONE.D
          }`}
        >
          {r.supply_grade}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-xs text-slate-400">{r.score.toFixed(0)}점</span>
        <span
          className={`flex items-center gap-1 text-sm font-extrabold tabular-nums ${changeColor}`}
        >
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {isUp ? "+" : ""}
          {r.change_pct.toFixed(1)}%
        </span>
      </div>
    </Link>
  );
}
