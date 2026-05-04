import { ContentAnalysis, StockReport } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { StockPriceBadge } from "@/components/StockPriceBadge";
import { SentimentChart } from "@/components/SentimentChart";
import { StockReportHistory } from "@/components/StockReportHistory";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

// 특정 종목의 데이터를 백엔드에서 가져오는 함수
async function getTickerContents(ticker: string): Promise<ContentAnalysis[]> {
  return apiFetch(`/api/contents/${ticker}`, []);
}

async function getStockName(ticker: string): Promise<string> {
  const data = await apiFetch<{ name: string }>(`/api/stock-name/${ticker}`, { name: ticker });
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

export default async function StockDetailPage({ params }: { params: { ticker: string } }) {
  // URL에서 티커 이름(예: NVDA)을 빼옵니다 (대문자로 통일)
  const resolvedParams = await Promise.resolve(params);
  const decodedTicker = decodeURIComponent(resolvedParams.ticker).toUpperCase();
  const [stockName, contents, history, stockReports] = await Promise.all([
    getStockName(decodedTicker),
    getTickerContents(decodedTicker),
    getStockHistory(decodedTicker),
    getStockReports(decodedTicker),
  ]);

  // DB에서 찾은 이름이 영문 티커와 다르면 기업명과 티커를 분리 표시
  const hasName = stockName !== decodedTicker;

  return (
    <main className="min-h-screen bg-slate-50 p-8 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl space-y-8">
        
        {/* 상단 헤더 & 뒤로가기 & 주가 뱃지 */}
        <div className="flex items-center gap-4 mb-6">
          <Link href="/" className="p-2 bg-white dark:bg-slate-900 rounded-full shadow hover:bg-slate-100 transition-colors">
            <ArrowLeft className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </Link>
          <div>
            <h1 className="text-3xl font-bold flex items-baseline text-slate-900 dark:text-slate-100 gap-4">
              {stockName} 집중 분석
              {hasName && <span className="text-lg font-medium text-slate-400 dark:text-slate-500">{decodedTicker}</span>}
              <StockPriceBadge ticker={decodedTicker} />
            </h1>
            <p className="text-slate-500 mt-1">AI가 수집한 최근 관련 뉴스 및 유튜브 감성 분석</p>
          </div>
        </div>

        {/* 데이터가 있을 경우 차트와 카드 표시 */}
        {contents.length > 0 ? (
          <>
            <SentimentChart data={contents} history={history} displayName={stockName} />
            <StockReportHistory reports={stockReports} />
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {contents.map((item) => (
                <ContentCard key={item.id} item={item} />
              ))}
            </div>
          </>
        ) : (
          /* 데이터가 없을 경우 안내 문구 */
          <div className="p-12 text-center bg-white dark:bg-slate-900 rounded-xl shadow-sm text-slate-500 border border-slate-200 dark:border-slate-800">
            아직 <strong>{decodedTicker}</strong>에 대해 AI가 수집한 데이터가 없습니다. <br/>
            (다른 종목을 검색하거나, 데이터 수집을 기다려주세요!)
          </div>
        )}
      </div>
    </main>
  );
}