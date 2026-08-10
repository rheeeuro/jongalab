import type { Metadata } from "next";
import { Suspense } from "react";
import {
  MacroEvent,
  MacroEventsResponse,
  MarketIndex,
  NewsHeatItem,
  SectorReport,
} from "@/types";
import {
  apiFetch,
  getRecordSummary,
  getReportDates,
  getRuleTitleMap,
  getStockReports,
} from "@/lib/api";
import { PickHero } from "@/components/pick/PickHero";
import { RecordStrip } from "@/components/pick/RecordStrip";
import { PickList } from "@/components/pick/PickList";
import { SeedAllocator } from "@/components/pick/SeedAllocator";
import { MacroEventNotice } from "@/components/pick/MacroEventNotice";
import {
  IndexChips,
  IndexChipsSkeleton,
  MarketPulse,
} from "@/components/home/MarketPulse";
import { NewsDigest } from "@/components/home/NewsDigest";

export const metadata: Metadata = {
  // 루트 page 는 루트 layout 의 title.template 적용 대상이 아니라(자식 세그먼트만 해당)
  // 접미사가 붙지 않는다 — 다른 화면과 형태를 맞추려면 여기서만 전체 문자열을 쓴다.
  title: { absolute: "오늘의 추천 · 종가랩" },
  description:
    "수급·기술·재료 데이터로 매 거래일 자동 선정한 추천 종목과 선정 근거, 그리고 지난 추천의 실제 성적.",
  alternates: { canonical: "/" },
};

// 오늘 밤 배너용 — 이틀치면 충분(오늘 남은 발표 + 내일 새벽 FOMC)
async function getMacroEvents(): Promise<MacroEvent[]> {
  const res = await apiFetch<MacroEventsResponse | null>(
    `/api/macro-events?days=2`,
    null,
  );
  return res?.events ?? [];
}

async function getSectors(date: string): Promise<SectorReport[]> {
  if (!date) return [];
  return apiFetch<SectorReport[]>(`/api/sector-report/${date}`, []);
}

async function getNewsHeat(date: string): Promise<NewsHeatItem[]> {
  if (!date) return [];
  const res = await apiFetch<{ success: boolean; data: NewsHeatItem[] } | null>(
    `/api/news/heat?date=${date}&limit=6`,
    null,
  );
  return res?.data ?? [];
}

// 외부 시세 API 라 1초 이상 걸리는 구간 — 추천 목록을 막지 않도록 Suspense 로 스트리밍한다.
async function IndexChipsSection() {
  const indices = await apiFetch<{
    US: MarketIndex[];
    KR: MarketIndex[];
  } | null>(`/api/market-indices`, null);
  return <IndexChips indices={indices} />;
}

export const dynamic = "force-dynamic";

/** 홈(추천 탭) — 종목 추천이 본체이고, 시장 지표는 **압축 요약**만 둔다.
 *
 * 화면은 `헤더 → 시장 칩 한 줄 → 매크로 경고 → (추천 | 성적·뉴스)` 순이다.
 * 지표를 픽 목록 위로 올린 건 예전 구조에서 카드 10장을 스크롤해야 지수·섹터가 나왔기
 * 때문이고, 칩 한 줄로 묶은 건 그래도 추천이 첫 화면을 유지해야 하기 때문이다.
 *
 * `/reports/{date}` 와 구성을 일부러 다르게 한다: 홈에만 최근 성적·매크로 경고·시장 요약이
 * 붙고, 날짜 이동과 그날 섹터 상세는 리포트 화면이 갖는다. 두 화면이 똑같으면 랜딩으로서의
 * 역할이 없어진다.
 */
export default async function HomePage() {
  // 기준일은 '오늘'이 아니라 **가장 최근 리포트일**이다 — 휴장일·장중에 화면이 통째로
  // 비지 않게 한다. 과거 날짜는 `/reports/{date}` 가 담당한다.
  const dates = await getReportDates(1);
  const date = dates[0] ?? "";

  const [reports, record, ruleTitleMap, macroEvents, sectors, newsHeat] =
    await Promise.all([
      getStockReports(date),
      getRecordSummary(20),
      getRuleTitleMap(),
      getMacroEvents(),
      getSectors(date),
      getNewsHeat(date),
    ]);

  // 이 날짜의 픽을 실제로 고른 고유 규칙 수 — 히어로 한 줄의 근거.
  const ruleCount = new Set(
    reports.flatMap((r) => (r.rule_names ?? "").split(",").filter(Boolean)),
  ).size;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6 sm:py-8">
        <PickHero date={date} pickCount={reports.length} ruleCount={ruleCount} />

        {/* 시장 지표는 추천 **위**에 둔다 — 칩 한 줄이라 픽을 밀어내지 않는다 */}
        <MarketPulse
          sectors={sectors}
          indexSlot={
            <Suspense fallback={<IndexChipsSkeleton />}>
              <IndexChipsSection />
            </Suspense>
          }
        />

        {/* 매크로 경고는 '오늘 밤' 기준이라 최신 리포트를 보는 홈에만 둔다 */}
        <MacroEventNotice events={macroEvents} />

        {/* 데스크탑(lg+)은 좌 추천 / 우 사이드바 2단. 모바일은 DOM 순서 그대로
            성적 → 추천 → 뉴스 로 쌓인다(사이드바를 통째로 위에 두면 픽이 밀린다).
            그래서 3개 자식을 명시적 그리드 좌표로 배치한다.
            `grid-rows-[auto_1fr]` 가 필수다 — 두 행이 다 auto 면 2행을 걸친 추천 목록의
            높이가 **두 행에 절반씩 나뉘어** 1행이 성적 카드보다 훨씬 커지고, 성적과 뉴스
            사이에 빈 공간이 생긴다. 2행을 flexible 로 두면 남는 높이를 2행이 흡수한다.

            **세로 간격(`gap-3`)은 카드 그리드 안쪽과 같은 값이어야 한다.** 우측 뉴스 카드는
            `성적 + 세로 간격` 아래에서 시작하고 좌측 2행(2·3·4등)은 `1등 카드 + gap-3` 아래에서
            시작하므로, 두 간격이 다르거나 두 카드 높이(`HERO_ROW_H`)가 다르면 상단이 틀어진다. */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_19rem] lg:grid-rows-[auto_1fr] lg:items-start lg:gap-x-6">
          <div className="lg:col-start-2 lg:row-start-1">
            <RecordStrip summary={record} />
          </div>

          <div className="lg:col-start-1 lg:row-start-1 lg:row-span-2">
            <PickList
              reports={reports}
              date={date}
              ruleTitleMap={ruleTitleMap}
              action={<SeedAllocator reports={reports} />}
            />
          </div>

          <div className="lg:col-start-2 lg:row-start-2">
            <NewsDigest items={newsHeat} date={date} />
          </div>
        </div>
      </div>
    </main>
  );
}
