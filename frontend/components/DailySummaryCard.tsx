import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  US: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  KR: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

export function DailySummaryCard({ summary, disableLink }: Props) {
  if (!summary) return null;

  const reportHref = `/report/${summary.report_date}`;

  const titleContent = (
    <CardTitle className={`flex items-center gap-2 text-xl ${!disableLink ? "group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" : ""}`}>
      🤖 오늘의 AI 투자 전략
      {summary.market && (
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${MARKET_STYLE[summary.market] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"}`}>
          {MARKET_LABEL[summary.market] || summary.market}
        </span>
      )}
    </CardTitle>
  );

  const dateContent = (
    <div className="flex items-center text-sm text-slate-500 bg-slate-100 px-3 py-1 rounded-full dark:bg-slate-800 shrink-0 w-fit">
      <Calendar className="w-4 h-4 mr-1" />
      {summary.report_date}
    </div>
  );

  return (
    <Card className={`border-2 border-slate-200 dark:border-slate-800 ${!disableLink ? "transition-all hover:border-indigo-200 hover:shadow-md dark:hover:border-indigo-900/70" : ""}`}>
      <CardHeader className="pb-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          {disableLink ? (
            <>
              {titleContent}
              {dateContent}
            </>
          ) : (
            <>
              <Link href={reportHref} className="group inline-block">
                {titleContent}
              </Link>
              <Link
                href={reportHref}
                aria-label={`${summary.report_date} AI 투자 리포트 보기`}
                className="group inline-flex w-fit items-center gap-1.5 rounded-full bg-indigo-600 px-4 py-2 text-sm font-bold text-white shadow-sm transition-all hover:bg-indigo-700 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
              >
                <FileText className="h-4 w-4" />
                오늘 리포트 보기
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          
          {/* 매수 추천 (Bull) */}
          <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-100 dark:border-green-900">
            <div className="flex items-center gap-2 mb-2 text-green-700 dark:text-green-400 font-bold text-lg">
              <TrendingUp className="w-6 h-6" />
              <span>강력 매수 (Buy)</span>
            </div>
            {summary.buy_ticker ? (
              <Link href={`/stock/${summary.buy_ticker}`} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-2 mb-3 sm:mb-2 group cursor-pointer">
                <span className="text-xl font-bold text-slate-800 dark:text-slate-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors underline decoration-indigo-200 dark:decoration-indigo-900 underline-offset-4">
                  {summary.buy_stock || '종목 없음'}
                </span>
                <StockPriceBadge ticker={summary.buy_ticker} />
              </Link>
            ) : (
              <div className="flex items-center mb-2">
                <span className="text-xl font-bold text-slate-800 dark:text-slate-100">
                  {summary.buy_stock || '종목 없음'}
                </span>
              </div>
            )}
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {summary.buy_reason}
            </p>
          </div>

          {/* 매도 추천 (Bear) */}
          <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-100 dark:border-red-900">
            <div className="flex items-center gap-2 mb-2 text-red-700 dark:text-red-400 font-bold text-lg">
              <TrendingDown className="w-6 h-6" />
              <span>매도/관망 (Sell)</span>
            </div>
            {summary.sell_ticker ? (
              <Link href={`/stock/${summary.sell_ticker}`} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-2 mb-3 sm:mb-2 group cursor-pointer">
                <span className="text-xl font-bold text-slate-800 dark:text-slate-100 group-hover:text-rose-600 dark:group-hover:text-rose-400 transition-colors underline decoration-rose-200 dark:decoration-rose-900 underline-offset-4">
                  {summary.sell_stock || '종목 없음'}
                </span>
                <StockPriceBadge ticker={summary.sell_ticker} />
              </Link>
            ) : (
              <div className="flex items-center mb-2">
                <span className="text-xl font-bold text-slate-800 dark:text-slate-100">
                  {summary.sell_stock || '종목 없음'}
                </span>
              </div>
            )}
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {summary.sell_reason}
            </p>
          </div>

        </div>
      </CardContent>
    </Card>
  );
}