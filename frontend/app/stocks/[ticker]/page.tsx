import { ContentAnalysis, StockReport } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { StockPriceBadge } from "@/components/StockPriceBadge";
import { SentimentChart } from "@/components/SentimentChart";
import { StockReportHistory } from "@/components/StockReportHistory";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";

async function getTickerContents(ticker: string): Promise<ContentAnalysis[]> {
  return apiFetch(`/api/contents/${ticker}`, []);
}

async function getStockName(ticker: string): Promise<string> {
  const data = await apiFetch<{ name: string }>(`/api/stock-name/${ticker}`, {
    name: ticker,
  });
  return data.name;
}

interface StockHistoryItem {
  date: string;
  price: number;
}

async function getStockHistory(ticker: string): Promise<StockHistoryItem[]> {
  return apiFetch(`/api/stock-history/${ticker}`, []);
}

async function getStockReports(ticker: string): Promise<StockReport[]> {
  return apiFetch(`/api/stock-report/history/${ticker}?limit=5`, []);
}

export default async function StockDetailPage({
  params,
}: {
  params: { ticker: string };
}) {
  const resolvedParams = await Promise.resolve(params);
  const decodedTicker = decodeURIComponent(resolvedParams.ticker).toUpperCase();
  const [stockName, contents, history, stockReports] = await Promise.all([
    getStockName(decodedTicker),
    getTickerContents(decodedTicker),
    getStockHistory(decodedTicker),
    getStockReports(decodedTicker),
  ]);

  const hasName = stockName !== decodedTicker;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        {/* 뒤로가기 */}
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          홈으로
        </Link>

        {/* 헤더 */}
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <Sparkles className="h-4 w-4 text-indigo-500" />
            <span>종목 집중 분석</span>
          </div>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <h1 className="text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
              {stockName}
            </h1>
            {hasName && (
              <span className="text-base font-bold text-slate-400 dark:text-slate-500">
                {decodedTicker}
              </span>
            )}
            <StockPriceBadge ticker={decodedTicker} />
          </div>
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
            AI가 수집한 뉴스·유튜브·텔레그램 콘텐츠의 감성 분석.
          </p>
        </header>

        {contents.length > 0 ? (
          <div className="space-y-8">
            <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
              <h2 className="mb-4 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
                감성 · 주가 흐름
              </h2>
              <SentimentChart
                data={contents}
                history={history}
                displayName={stockName}
              />
            </section>

            <StockReportHistory reports={stockReports} />

            <section>
              <h2 className="mb-4 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-xl">
                관련 콘텐츠
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                {contents.map((item) => (
                  <ContentCard key={item.id} item={item} />
                ))}
              </div>
            </section>
          </div>
        ) : (
          <div className="rounded-3xl bg-white p-12 text-center dark:bg-slate-900/60">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              아직 <strong className="text-slate-900 dark:text-slate-100">{decodedTicker}</strong>에 대해
              <br />
              AI가 수집한 데이터가 없습니다.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
