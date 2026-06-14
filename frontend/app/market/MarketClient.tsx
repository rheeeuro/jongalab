"use client";

import { MarketIndicesSection } from "@/components/MarketIndicesSection";
import { LineChart } from "lucide-react";

export function MarketClient() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        {/* 헤더 */}
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <LineChart className="h-4 w-4 text-indigo-500" />
            <span>실시간 시장</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            지금 이 순간의
            <br />
            시장 흐름.
          </h1>
        </div>

        <MarketIndicesSection />
      </div>
    </main>
  );
}
