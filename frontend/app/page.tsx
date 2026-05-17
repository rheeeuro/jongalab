import { ContentAnalysis, DailySummary, MentionStats, MarketIndex, PaginatedResponse, SectorReport } from "@/types";
import { apiFetch } from "@/lib/api";
import { TodayHero } from "@/components/today/TodayHero";
import { TopPicks } from "@/components/today/TopPicks";
import { LeadingSectorsStrip } from "@/components/today/LeadingSectorsStrip";
import { MentionPulse } from "@/components/today/MentionPulse";
import { ContentTeaser } from "@/components/today/ContentTeaser";
import { RecentReportsRow } from "@/components/today/RecentReportsRow";
import { IndicesStrip } from "@/components/today/IndicesStrip";

async function getContents(market: string): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch(`/api/contents?page=1&limit=6&market=${market}`, {
    success: false,
    data: [],
    pagination: null,
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

export default async function HomePage(props: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await props.searchParams;
  const market = (params?.market as string) || "ALL";

  const [contents, summary, summaryList, mentionStats, sectorReport, indices] =
    await Promise.all([
      getContents(market),
      getDailySummary(market),
      getDailySummaryList(market),
      getMentionStats(market),
      getLatestSectorReport(),
      getMarketIndices(),
    ]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10 lg:space-y-10">
        <TodayHero summary={summary} mentionStats={mentionStats} />
        <TopPicks summary={summary} />
        <IndicesStrip indices={indices} market={market} />
        <LeadingSectorsStrip sectors={sectorReport} />
        <MentionPulse stats={mentionStats} />
        <ContentTeaser items={contents.data || []} market={market} />
        <RecentReportsRow reports={summaryList} />
      </div>
    </main>
  );
}
