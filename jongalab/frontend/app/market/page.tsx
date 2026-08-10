import type { Metadata } from "next";
import { Layers, LineChart } from "lucide-react";
import { MentionStats, SectorReport } from "@/types";
import { apiFetch, getReportDates } from "@/lib/api";
import { MarketClient } from "./MarketClient";
import { SectorBoard } from "@/components/market/SectorBoard";
import { ViewSegment } from "@/components/ViewSegment";

export const metadata: Metadata = {
  title: "시장",
  description: "지수·경제 일정과 주도 섹터를 나눠서 봅니다.",
  alternates: { canonical: "/market" },
};

type View = "index" | "sector";

async function getLatestSectorReport(): Promise<{
  date: string;
  sectors: SectorReport[];
}> {
  const dates = await getReportDates(1);
  if (!dates.length) return { date: "", sectors: [] };
  return {
    date: dates[0],
    sectors: await apiFetch<SectorReport[]>(`/api/sector-report/${dates[0]}`, []),
  };
}

async function getMentionStats(): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats`,
    null,
  );
  return res?.success ? res.data : null;
}

export const dynamic = "force-dynamic";

/** 시장 탭 — **지수**와 **섹터**를 세그먼트로 나눈다.
 *
 * 한 화면에 지수 카드와 섹터 랭킹을 쌓으면 모바일에서 섹터까지 스크롤이 너무 길다.
 * 탭을 늘리지 않고(`lib/nav.ts` 목적지 5개 고정) 화면 안에서만 가르므로 URL 은
 * `?view=sector` 쿼리다 — canonical 은 `/market` 하나로 유지된다.
 */
export default async function MarketPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const sp = await searchParams;
  const view: View = sp.view === "sector" ? "sector" : "index";

  // 섹터 뷰에서만 쓰는 데이터는 그 뷰일 때만 부른다 — 기본(지수) 뷰의 왕복을 줄인다.
  const isSector = view === "sector";
  const [{ date, sectors }, mentionStats] = isSector
    ? await Promise.all([getLatestSectorReport(), getMentionStats()])
    : [{ date: "", sectors: [] as SectorReport[] }, null];

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-5 sm:px-6 sm:py-8">
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <LineChart className="h-4 w-4 text-indigo-500" />
            <span>시장 배경</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            시장
          </h1>
          <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
            추천 종목이 놓인 배경 — 지수와 주도 섹터를 나눠서 봅니다.
          </p>
        </header>

        <ViewSegment
          active={view}
          options={[
            { key: "index", label: "지수", icon: LineChart, href: "/market" },
            {
              key: "sector",
              label: "섹터",
              icon: Layers,
              href: "/market?view=sector",
            },
          ]}
        />

        {view === "index" ? (
          <MarketClient />
        ) : (
          <SectorBoard
            sectors={sectors}
            date={date}
            mentionStats={mentionStats}
          />
        )}
      </div>
    </main>
  );
}
