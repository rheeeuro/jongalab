import { ContentAnalysis, DailySummary, MentionStats, MarketIndex, PaginatedResponse, SectorReport } from "@/types";
import { apiFetch } from "@/lib/api";
import { TodayHero } from "@/components/today/TodayHero";
import { TopPicks } from "@/components/today/TopPicks";
import { LeadingSectorsStrip } from "@/components/today/LeadingSectorsStrip";
import { MentionPulse } from "@/components/today/MentionPulse";
import { ContentTeaser } from "@/components/today/ContentTeaser";
import { RecentReportsRow } from "@/components/today/RecentReportsRow";
import { IndicesStrip } from "@/components/today/IndicesStrip";

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

async function getDailySummaryList(): Promise<DailySummary[]> {
  return apiFetch(`/api/daily-summary-list?limit=5`, []);
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

export default async function HomePage() {
  const [contents, summary, summaryList, mentionStats, sectorReport, indices] =
    await Promise.all([
      getContents(),
      getDailySummary(),
      getDailySummaryList(),
      getMentionStats(),
      getLatestSectorReport(),
      getMarketIndices(),
    ]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10 lg:space-y-10">
        <TodayHero summary={summary} mentionStats={mentionStats} />
        <TopPicks summary={summary} />
        <IndicesStrip indices={indices} />
        <LeadingSectorsStrip sectors={sectorReport} />
        <MentionPulse stats={mentionStats} />
        <ContentTeaser items={contents.data || []} />
        <RecentReportsRow reports={summaryList} />
      </div>
    </main>
  );
}
