import { ContentAnalysis, StockReport, MentionStats, MarketIndex, PaginatedResponse, SectorReport, NewsHeatItem } from "@/types";
import { apiFetch } from "@/lib/api";
import { TodayHero } from "@/components/today/TodayHero";
import { TopPicks } from "@/components/today/TopPicks";
import { LeadingSectorsStrip } from "@/components/today/LeadingSectorsStrip";
import { MentionPulse } from "@/components/today/MentionPulse";
import { NewsHeat } from "@/components/today/NewsHeat";
import { ContentTeaser } from "@/components/today/ContentTeaser";
import { IndicesStrip, IndicesStripSkeleton } from "@/components/today/IndicesStrip";
import { Suspense } from "react";

async function getContents(): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch(`/api/contents?page=1&limit=6`, {
    success: false,
    data: [],
    pagination: null,
  });
}

// 최신 영업일의 종목 랭킹 1위(rank_no=1)를 오늘의 추천으로 사용한다.
async function getLatestTopPick(): Promise<StockReport | null> {
  const dates = await apiFetch<string[]>(`/api/stock-report/dates?limit=1`, []);
  if (!dates.length) return null;
  const reports = await apiFetch<StockReport[]>(
    `/api/stock-report/${dates[0]}`,
    [],
  );
  return reports[0] ?? null;
}

async function getMentionStats(): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats`,
    null,
  );
  return res?.success ? res.data : null;
}

async function getNewsHeat(): Promise<NewsHeatItem[]> {
  const res = await apiFetch<{ success: boolean; data: NewsHeatItem[] } | null>(
    `/api/news/heat?hours=24&limit=10`,
    null,
  );
  return res?.success ? res.data : [];
}

async function getLatestSectorReport(): Promise<SectorReport[]> {
  const dates = await apiFetch<string[]>(`/api/stock-report/dates?limit=1`, []);
  if (!dates.length) return [];
  return apiFetch<SectorReport[]>(`/api/sector-report/${dates[0]}`, []);
}

async function getMarketIndices(): Promise<{
  US: MarketIndex[];
  KR: MarketIndex[];
  COMMODITIES: MarketIndex[];
} | null> {
  return apiFetch(`/api/market-indices`, null);
}

export const dynamic = "force-dynamic";

// 시세 외부 API 호출로 1초 이상 걸리는 구간. 나머지 빠른 콘텐츠를 막지 않도록
// 별도 async 컴포넌트로 분리해 Suspense로 스트리밍한다.
async function IndicesSection() {
  const indices = await getMarketIndices();
  return <IndicesStrip indices={indices} />;
}

export default async function HomePage() {
  const [contents, topPick, mentionStats, sectorReport, newsHeat] =
    await Promise.all([
      getContents(),
      getLatestTopPick(),
      getMentionStats(),
      getLatestSectorReport(),
      getNewsHeat(),
    ]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10 lg:space-y-10">
        <TodayHero reportDate={topPick?.report_date ?? null} mentionStats={mentionStats} />
        <TopPicks pick={topPick} />
        <Suspense fallback={<IndicesStripSkeleton />}>
          <IndicesSection />
        </Suspense>
        <LeadingSectorsStrip sectors={sectorReport} />
        <MentionPulse stats={mentionStats} />
        <NewsHeat items={newsHeat} />
        <ContentTeaser items={contents.data || []} />
      </div>
    </main>
  );
}
