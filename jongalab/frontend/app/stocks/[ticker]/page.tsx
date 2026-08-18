import type { Metadata } from "next";
import { ContentAnalysis, NewsMentionItem, StockReport } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { StockPriceBadge } from "@/components/StockPriceBadge";
import { SentimentChart } from "@/components/SentimentChart";
import { StockReportHistory } from "@/components/StockReportHistory";
import { TodayNews } from "@/components/TodayNews";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { ArrowLeft, Sparkles } from "lucide-react";

export async function generateMetadata({
  params,
}: {
  params: { ticker: string };
}): Promise<Metadata> {
  const resolvedParams = await Promise.resolve(params);
  const decodedTicker = decodeURIComponent(resolvedParams.ticker).toUpperCase();
  const [stockName, contents, stockReports] = await Promise.all([
    getStockName(decodedTicker),
    getTickerContents(decodedTicker),
    getStockReports(decodedTicker),
  ]);

  // 수집 콘텐츠도 리포트 이력도 없으면 화면이 "데이터가 없습니다" 한 줄뿐이라 색인에서 뺀다
  // (사이트맵도 같은 기준으로 리포트 있는 종목만 싣는다). 근거: docs/plan/seo/search-visibility.md
  const hasContent = contents.length > 0 || stockReports.length > 0;

  // 날짜가 붙는 리포트 상세(`{종목명} 투자분석 - YYYY.MM.DD`)와 달리 여기는 **상시** 페이지다.
  // 제목에 날짜를 넣지 않아 종목 이름만으로 찾는 질의를 이 화면이 받는다.
  const description =
    stockReports.length > 0
      ? `${stockName}(${decodedTicker}) 종목 분석 — 종가베팅 후보로 선정된 이력 ${stockReports.length}건과 그때의 선정 근거, 수급·뉴스 재료를 한 화면에 모았습니다.`
      : `${stockName}(${decodedTicker}) 종목 분석 — 수집한 뉴스·콘텐츠에서 이 종목이 어떻게 언급됐는지 모아 봅니다.`;

  return {
    title: `${stockName} 종목 분석`,
    description,
    alternates: { canonical: `/stocks/${decodedTicker}` },
    ...(hasContent ? {} : { robots: { index: false, follow: true } }),
  };
}

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

async function getTodayNews(ticker: string): Promise<NewsMentionItem[]> {
  const res = await apiFetch<{ success: boolean; data: NewsMentionItem[] }>(
    `/api/news/${ticker}`,
    { success: false, data: [] },
  );
  return res.data ?? [];
}

export default async function StockDetailPage({
  params,
}: {
  params: { ticker: string };
}) {
  const resolvedParams = await Promise.resolve(params);
  const decodedTicker = decodeURIComponent(resolvedParams.ticker).toUpperCase();
  const [stockName, contents, history, stockReports, todayNews] =
    await Promise.all([
      getStockName(decodedTicker),
      getTickerContents(decodedTicker),
      getStockHistory(decodedTicker),
      getStockReports(decodedTicker),
      getTodayNews(decodedTicker),
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

        <div className="space-y-8">
          <TodayNews items={todayNews} />

          {contents.length > 0 ? (
            <>
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
            </>
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
      </div>
    </main>
  );
}
