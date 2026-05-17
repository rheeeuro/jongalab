import { StockReport } from "@/types";
import { apiFetch } from "@/lib/api";
import { StocksBrowser } from "./StocksBrowser";
import { CandlestickChart } from "lucide-react";

async function getLatestStockReports(): Promise<{
  date: string;
  reports: StockReport[];
}> {
  const dates = await apiFetch<string[]>("/api/stock-report/dates?limit=1", []);
  if (!dates.length) return { date: "", reports: [] };
  const reports = await apiFetch<StockReport[]>(
    `/api/stock-report/${dates[0]}`,
    [],
  );
  return { date: dates[0], reports };
}

export const dynamic = "force-dynamic";

export default async function StocksIndexPage() {
  const { date, reports } = await getLatestStockReports();

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <CandlestickChart className="h-4 w-4 text-indigo-500" />
            <span>종목 둘러보기</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            오늘 시장을 이끄는
            <br />
            종목들.
          </h1>
          {date && (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
              기준일: <span className="font-bold">{date}</span> · 총{" "}
              <span className="font-bold">{reports.length}</span>개 종목
            </p>
          )}
        </header>

        <StocksBrowser reports={reports} date={date} />
      </div>
    </main>
  );
}
