import { ContentAnalysis, DailySummary, MentionStats, MarketIndex, PaginatedResponse, SectorReport } from "@/types";
import { apiFetch } from "@/lib/api";
import { TodayHero } from "@/components/today/TodayHero";
import { TopPicks } from "@/components/today/TopPicks";
import { LeadingSectorsStrip } from "@/components/today/LeadingSectorsStrip";
import { MentionPulse } from "@/components/today/MentionPulse";
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

async function getDailySummary(): Promise<DailySummary | null> {
  return apiFetch(`/api/daily-summary`, null);
}

async function getMentionStats(): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats`,
    null,
  );
  return res?.success ? res.data : null;
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
  const [contents, summary, mentionStats, sectorReport] =
    await Promise.all([
      getContents(),
      getDailySummary(),
      getMentionStats(),
      getLatestSectorReport(),
    ]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10 lg:space-y-10">
        <TodayHero summary={summary} mentionStats={mentionStats} />
        <TopPicks summary={summary} />
        <Suspense fallback={<IndicesStripSkeleton />}>
          <IndicesSection />
        </Suspense>
        <LeadingSectorsStrip sectors={sectorReport} />
        <MentionPulse stats={mentionStats} />
        <ContentTeaser items={contents.data || []} />
      </div>
    </main>
  );
}
