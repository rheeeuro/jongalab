"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import type { MarketIndex, StockReport } from "@/types";
import { MarketIndicesSection } from "@/components/MarketIndicesSection";
import {
  Crown,
  TrendingUp,
  TrendingDown,
  BarChart3,
} from "lucide-react";

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

async function getLatestStockReports(): Promise<{ date: string; reports: StockReport[] }> {
  const dates = await clientFetch<string[]>("/api/stock-report/dates?limit=1", []);
  if (dates.length === 0) return { date: "", reports: [] };
  const reports = await clientFetch<StockReport[]>(`/api/stock-report/${dates[0]}`, []);
  return { date: dates[0], reports };
}

export function DashboardClient() {
  const searchParams = useSearchParams();
  const currentMarket = searchParams.get("market") || "ALL";
  const showUS = currentMarket === "ALL" || currentMarket === "US";
  const showKR = currentMarket === "ALL" || currentMarket === "KR";

  const [usLeaders, setUsLeaders] = useState<MarketIndex[]>([]);
  const [krLeaders, setKrLeaders] = useState<MarketIndex[]>([]);
  const [latestReports, setLatestReports] = useState<{ date: string; reports: StockReport[] }>({
    date: "",
    reports: [],
  });
  const [leadersLoading, setLeadersLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboardData() {
      setLeadersLoading(true);

      const [nextUsLeaders, nextKrLeaders, nextLatestReports] = await Promise.all([
        showUS ? clientFetch<MarketIndex[]>("/api/market-leaders/US", []) : Promise.resolve([]),
        showKR ? clientFetch<MarketIndex[]>("/api/market-leaders/KR", []) : Promise.resolve([]),
        showKR ? getLatestStockReports() : Promise.resolve({ date: "", reports: [] }),
      ]);

      if (cancelled) return;
      setUsLeaders(nextUsLeaders);
      setKrLeaders(nextKrLeaders);
      setLatestReports(nextLatestReports);
      setLeadersLoading(false);
    }

    loadDashboardData();

    return () => {
      cancelled = true;
    };
  }, [showUS, showKR]);

  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-8 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl space-y-8">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            <BarChart3 className="h-6 w-6 text-indigo-500" />
            시황 대시보드
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            주요 시장 지표와 주도주 현황을 한눈에 확인하세요.
          </p>
        </div>

        <MarketIndicesSection showUS={showUS} showKR={showKR} />

        <div className={`grid gap-8 ${showUS && showKR ? "lg:grid-cols-2" : ""}`}>
          {showUS && (
            <Section
              icon={<TrendingUp className="h-5 w-5 text-blue-500" />}
              title="미국 주도주"
            >
              <LeaderList items={usLeaders} loading={leadersLoading} />
            </Section>
          )}

          {showKR && (
            <Section
              icon={<TrendingUp className="h-5 w-5 text-red-500" />}
              title="한국 주도주"
            >
              {latestReports.reports.length > 0 ? (
                <div className="space-y-2">
                  {latestReports.reports.map((r) => (
                    <StockReportRow key={r.stock_code} report={r} date={latestReports.date} />
                  ))}
                </div>
              ) : (
                <LeaderList items={krLeaders} loading={leadersLoading} />
              )}
            </Section>
          )}
        </div>
      </div>
    </main>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function LeaderList({ items, loading }: { items: MarketIndex[]; loading: boolean }) {
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
    ? "text-red-600 dark:text-red-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500";

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;

  const isKr =
    item.symbol.endsWith(".KS") || item.symbol.endsWith(".KQ");
  const priceStr = isKr
    ? `₩${item.price.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}`
    : `$${item.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <Link
      href={`/stock/${item.symbol}`}
      className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 transition-colors hover:border-indigo-300 hover:bg-indigo-50/50 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/30"
    >
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
          {item.name}
        </span>
        <span className="text-xs text-slate-400">{item.symbol}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          {priceStr}
        </span>
        <span className={`flex items-center gap-1 text-sm font-semibold ${changeColor}`}>
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {isUp ? "+" : ""}
          {item.change_percent?.toFixed(2)}%
        </span>
      </div>
    </Link>
  );
}

const GRADE_STYLE: Record<string, string> = {
  S: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
  A: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400",
  B: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400",
  C: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  D: "bg-slate-50 text-slate-500 dark:bg-slate-900 dark:text-slate-500",
};

function StockReportRow({ report: r, date }: { report: StockReport; date: string }) {
  const isUp = r.change_pct > 0;
  const isDown = r.change_pct < 0;
  const changeColor = isUp
    ? "text-red-600 dark:text-red-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500";
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;

  return (
    <Link
      href={`/report/${date}/${r.stock_code}`}
      className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 transition-colors hover:border-indigo-300 hover:bg-indigo-50/50 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/30"
    >
      <div className="flex items-center gap-3">
        <span className="w-6 text-center text-xs font-bold text-indigo-500">{r.rank_no}</span>
        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
          {r.stock_name}
        </span>
        {r.is_leader && <Crown className="h-3.5 w-3.5 text-amber-500" />}
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${GRADE_STYLE[r.supply_grade] || GRADE_STYLE.D}`}>
          수급{r.supply_grade} | {r.supply_score?.toFixed(0) ?? 0}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-400">{r.score.toFixed(0)}점</span>
        <span className={`flex items-center gap-1 text-sm font-semibold ${changeColor}`}>
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {isUp ? "+" : ""}{r.change_pct.toFixed(1)}%
        </span>
      </div>
    </Link>
  );
}
