import { ContentAnalysis, DailySummary, MentionStats, PaginatedResponse } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { DailySummaryCard } from "@/components/DailySummaryCard";
import { MentionTreemapCard } from "@/components/MentionTreemapCard";
import { apiFetch } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { Calendar, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";

async function getContents(page: number, limit: number, market: string): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch(`/api/contents?page=${page}&limit=${limit}&market=${market}`, {
    success: false, data: [], pagination: null,
  });
}

async function getDailySummary(market: string): Promise<DailySummary | null> {
  return apiFetch(`/api/daily-summary?market=${market}`, null);
}

async function getDailySummaryList(market: string): Promise<DailySummary[]> {
  return apiFetch(`/api/daily-summary-list?limit=5&market=${market}`, []);
}

async function getMentionStats(market: string): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats?market=${market}`,
    null,
  );
  return res?.success ? res.data : null;
}

export const dynamic = 'force-dynamic';

export default async function Home(props: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await props.searchParams;

  const currentMarket = (params?.market as string) || "ALL";
  const currentPage = Number(params?.page) || 1;
  const limit = 12;

  const [contentsRes, summary, summaryList, mentionStats] = await Promise.all([
    getContents(currentPage, limit, currentMarket),
    getDailySummary(currentMarket),
    getDailySummaryList(currentMarket),
    getMentionStats(currentMarket),
  ]);

  // 백엔드 응답에서 실제 데이터 배열과 페이지네이션 정보를 분리
  const data = contentsRes.data || [];
  const pagination = contentsRes.pagination;

  return (
    <main className="min-h-screen bg-slate-50 p-8 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl space-y-8">
        
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-indigo-500" />
              콘텐츠 분석
            </h1>
            <p className="text-slate-500 mt-1 text-sm hidden sm:block">
              YouTube 및 Telegram 데이터를 실시간 분석합니다.
            </p>
          </div>
          <Badge variant="outline" className="px-3 py-1 bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 whitespace-nowrap shrink-0">
            Weekly: {pagination?.total_items || 0}
          </Badge>
        </div>

        {/* 요약 카드 */}
        <DailySummaryCard summary={summary} />

        {/* 섹터·기업 언급 트리맵 (최근 12시간) */}
        <MentionTreemapCard stats={mentionStats} />

        {summaryList.length > 0 && (
          <div className="mt-12 mb-8 bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2 text-slate-800 dark:text-slate-100">
                <Calendar className="w-5 h-5 text-indigo-500" />
                지난 AI 투자 리포트
              </h2>
            </div>
            
            {/* 리포트 카드 그리드 (가로 정렬) */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {summaryList.map((report) => (
                <Link key={report.id} href={`/report/${report.report_date}`}>
                  <div className="group p-4 border border-slate-100 dark:border-slate-800 rounded-lg hover:border-indigo-500 hover:shadow-md transition-all cursor-pointer bg-slate-50 dark:bg-slate-950 flex flex-col h-full relative overflow-hidden">
                    <span className="text-xs text-slate-400 font-medium mb-1 flex items-center justify-between">
                      <span className="flex items-center gap-1">
                        {report.report_date}
                        {report.market && (
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            report.market === 'US' ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300' : 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300'
                          }`}>
                            {report.market}
                          </span>
                        )}
                      </span>
                      <ChevronRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-500" />
                    </span>
                    <span className="font-bold text-slate-700 dark:text-slate-200 text-sm line-clamp-1">
                      {report.buy_stock || '추천 종목'}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* ✅ 콘텐츠 카드 그리드 */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((item) => (
            <ContentCard key={item.id} item={item} />
          ))}
        </div>

        {pagination && pagination.total_pages > 1 && (
          <div className="pt-8 flex items-center justify-center gap-4">
            {pagination.has_prev_page ? (
              <Link
                href={`/?market=${currentMarket}&page=${pagination.current_page - 1}`}
                className="flex items-center gap-1 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 shadow-sm transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
                이전
              </Link>
            ) : (
              <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-400 cursor-not-allowed dark:border-slate-800 dark:bg-slate-950 dark:text-slate-600">
                <ChevronLeft className="w-4 h-4" />
                이전
              </div>
            )}
            
            <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
              Page {pagination.current_page} of {pagination.total_pages}
            </span>

            {pagination.has_next_page ? (
              <Link
                href={`/?market=${currentMarket}&page=${pagination.current_page + 1}`}
                className="flex items-center gap-1 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 shadow-sm transition-colors"
              >
                다음
                <ChevronRight className="w-4 h-4" />
              </Link>
            ) : (
              <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-400 cursor-not-allowed dark:border-slate-800 dark:bg-slate-950 dark:text-slate-600">
                다음
                <ChevronRight className="w-4 h-4" />
              </div>
            )}
          </div>
        )}
        
      </div>
    </main>
  );
}