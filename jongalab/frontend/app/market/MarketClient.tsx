"use client";

import { MarketIndicesSection } from "@/components/MarketIndicesSection";
import { MacroEventsCard } from "@/components/MacroEventsCard";

/** 지수·경제 일정 — 실시간 폴링이 필요한 부분만 클라이언트로 남긴다.
 * 헤더·감성·섹터는 서버 컴포넌트(`page.tsx`)가 렌더한다. */
export function MarketClient() {
  return (
    <div className="space-y-6">
      <MarketIndicesSection />
      <MacroEventsCard />
    </div>
  );
}
