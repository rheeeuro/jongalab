"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Wallet } from "lucide-react";
import { StockReport } from "@/types";

const LS_KEY_SEED = "seedAllocator_seed";
const PREVIEW_COUNT = 8;
// 배분 대상 후보 수 상한 — 점수 상위 N개만 매수 (trading/core/seed_allocator.py 와 동일)
const TOP_N = 10;
// 종목당 최대 투입 비율 — 미리보기용 기본값.
// 실거래(trading)는 .env(SEED_MAX_NAME_PCT)로 튜닝하며,
// 이 미리보기는 백엔드 기본값과 동일한 값으로 고정한다(프론트는 trading .env 미접근).
const MAX_NAME_PCT = 0.5;

const QUICK_AMOUNTS = [
  { label: "100만", value: 1_000_000 },
  { label: "500만", value: 5_000_000 },
  { label: "1,000만", value: 10_000_000 },
  { label: "5,000만", value: 50_000_000 },
];

type Allocation = {
  report: StockReport;
  weight: number;
  allocAmount: number;
  shares: number;
  cost: number;
};

export function SeedAllocator({ reports }: { reports: StockReport[] }) {
  const [seed, setSeed] = useState("");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(LS_KEY_SEED);
    if (stored) setSeed(stored);
  }, []);

  useEffect(() => {
    if (seed) localStorage.setItem(LS_KEY_SEED, seed);
    else localStorage.removeItem(LS_KEY_SEED);
  }, [seed]);

  const seedNum = Number(seed.replace(/[^0-9]/g, "")) || 0;

  const allocations = useMemo<Allocation[]>(() => {
    if (seedNum <= 0 || reports.length === 0) return [];

    // 유효가(>0) 후보를 점수순으로 정렬해 상위 TOP_N 개만 배분 대상으로 삼는다(선정 컷).
    const ranked = reports
      .filter((r) => r.current_price > 0)
      .sort((a, b) => Math.max(b.score, 0) - Math.max(a.score, 0))
      .slice(0, TOP_N);

    // 등가중: 선정된 종목엔 동일 목표금액. (점수는 선정 컷에만 쓰고 사이징엔 안 씀 —
    // 실거래상 점수가 익일 청산 손익을 예측 못 해 점수비례 집중을 제거했다. trading/core/seed_allocator.py 와 동일)
    const items = ranked.map((r) => ({
      report: r,
      price: r.current_price,
      shares: 0,
      cost: 0,
    }));
    const n = items.length;
    if (n === 0) return [];

    // 종목당 최대 투입금액 — 시드 대비 비율 캡(이 금액을 넘게는 배분하지 않는다).
    const cap = seedNum * MAX_NAME_PCT;

    // 1차: 등가중 목표금액(캡 적용) → 정수 주식으로 내림 배분
    for (const it of items) {
      const target = Math.min(seedNum / n, cap);
      it.shares = Math.floor(target / it.price);
      it.cost = it.shares * it.price;
    }

    // 2차: 잔여 현금을 그리디로 재투입 — 현재 투입액이 가장 적은 종목부터 한 주씩 추가
    // 매수해 배분을 균형 있게 채운다(등가중이라 상위 집중이 아니라 최소 투입 우선). 한 주 더
    // 사면 종목당 캡(cap)을 넘는 종목은 제외하며, 매수 가능 종목이 없을 때까지(잔여 < 최저가
    // 또는 전원 캡 도달) 채운다.
    let leftover = seedNum - items.reduce((s, it) => s + it.cost, 0);
    for (;;) {
      let best: (typeof items)[number] | null = null;
      let bestCost = Infinity;
      for (const it of items) {
        if (it.price <= 0 || it.price > leftover) continue;
        if (it.cost + it.price > cap) continue;
        if (it.cost < bestCost) {
          bestCost = it.cost;
          best = it;
        }
      }
      if (!best) break;
      best.shares += 1;
      best.cost += best.price;
      leftover -= best.price;
    }

    return items
      .map((it) => ({
        report: it.report,
        weight: 1 / n,
        allocAmount: Math.min(seedNum / n, cap),
        shares: it.shares,
        cost: it.cost,
      }))
      .sort((a, b) => b.cost - a.cost);
  }, [reports, seedNum]);

  const buyable = allocations.filter((a) => a.shares > 0);
  const totalInvested = buyable.reduce((s, a) => s + a.cost, 0);
  const leftover = Math.max(seedNum - totalInvested, 0);
  const utilizationPct = seedNum > 0 ? (totalInvested / seedNum) * 100 : 0;

  function handleSeedChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value.replace(/[^0-9]/g, "");
    setSeed(raw ? Number(raw).toLocaleString("ko-KR") : "");
  }

  function quickSet(value: number) {
    setSeed(value.toLocaleString("ko-KR"));
  }

  const showResults = seedNum > 0 && reports.length > 0;
  const displayList = expanded ? buyable : buyable.slice(0, PREVIEW_COUNT);

  return (
    <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <header className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
          <Wallet className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-extrabold text-slate-900 dark:text-slate-100 sm:text-lg">
            시드 배분
          </h2>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            점수 상위 {Math.min(reports.length, TOP_N)}개 종목에 균등(등가중) 배분
          </p>
        </div>
      </header>

      <div className="mt-4">
        <div className="relative">
          <input
            inputMode="numeric"
            value={seed}
            onChange={handleSeedChange}
            placeholder="총 시드 금액"
            className="w-full rounded-2xl bg-slate-50 px-4 py-3 pr-10 text-lg font-extrabold tabular-nums text-slate-900 placeholder:text-base placeholder:font-medium placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 dark:bg-slate-800/60 dark:text-slate-100"
          />
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-sm font-bold text-slate-400">
            원
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {QUICK_AMOUNTS.map((q) => (
            <button
              key={q.value}
              type="button"
              onClick={() => quickSet(q.value)}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600 transition-colors hover:bg-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {q.label}
            </button>
          ))}
          {seed && (
            <button
              type="button"
              onClick={() => setSeed("")}
              className="rounded-full px-3 py-1 text-xs font-bold text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              초기화
            </button>
          )}
        </div>
      </div>

      {showResults && (
        <>
          <div className="mt-5 grid grid-cols-3 gap-2 rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/40">
            <Stat label="활용률" value={`${utilizationPct.toFixed(1)}%`} />
            <Stat
              label="매수금"
              value={`${totalInvested.toLocaleString("ko-KR")}원`}
            />
            <Stat
              label="잔여 현금"
              value={`${leftover.toLocaleString("ko-KR")}원`}
            />
          </div>

          <div className="mt-4">
            <p className="text-xs font-extrabold text-slate-600 dark:text-slate-300">
              매수 가능 종목 {buyable.length}개
            </p>
            {buyable.length === 0 ? (
              <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
                시드가 부족해 매수할 수 있는 종목이 없습니다. 시드를 늘리거나
                검색으로 종목 수를 줄여보세요.
              </p>
            ) : (
              <>
                <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800/60">
                  {displayList.map((a) => (
                    <AllocationRow
                      key={a.report.stock_code}
                      alloc={a}
                      totalInvested={totalInvested}
                    />
                  ))}
                </ul>
                {buyable.length > PREVIEW_COUNT && (
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="mt-3 flex w-full items-center justify-center gap-1 rounded-xl py-2 text-xs font-bold text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950/30"
                  >
                    {expanded ? (
                      <>
                        접기 <ChevronUp className="h-3.5 w-3.5" />
                      </>
                    ) : (
                      <>
                        {buyable.length - PREVIEW_COUNT}개 더 보기{" "}
                        <ChevronDown className="h-3.5 w-3.5" />
                      </>
                    )}
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-extrabold tabular-nums text-slate-900 dark:text-slate-100">
        {value}
      </p>
    </div>
  );
}

function AllocationRow({
  alloc,
  totalInvested,
}: {
  alloc: Allocation;
  totalInvested: number;
}) {
  const { report: r, shares, cost } = alloc;
  const actualPct = totalInvested > 0 ? (cost / totalInvested) * 100 : 0;
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
            {r.stock_name}
          </span>
          <span className="shrink-0 text-[10px] font-bold text-slate-400">
            {r.stock_code}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
          {r.current_price.toLocaleString("ko-KR")}원 · 비중{" "}
          {actualPct.toFixed(1)}%
        </p>
      </div>
      <div className="shrink-0 text-right tabular-nums">
        <p className="text-sm font-extrabold text-indigo-600 dark:text-indigo-400">
          {shares}주
        </p>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          {cost.toLocaleString("ko-KR")}원
        </p>
      </div>
    </li>
  );
}
