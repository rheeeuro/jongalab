"use client";

import { useMemo, useState } from "react";
import { StockReport } from "@/types";
import { Search } from "lucide-react";
import { SeedAllocator } from "./SeedAllocator";
import { StockReportCard } from "@/components/StockReportCard";

type SortKey = "rank" | "score" | "change" | "supply";

export function StocksBrowser({
  reports,
  date,
}: {
  reports: StockReport[];
  date: string;
}) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("rank");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let result = q
      ? reports.filter(
          (r) =>
            r.stock_name.toLowerCase().includes(q) ||
            r.stock_code.toLowerCase().includes(q) ||
            (r.sector ?? "").toLowerCase().includes(q),
        )
      : [...reports];

    result.sort((a, b) => {
      switch (sortKey) {
        case "score":
          return b.score - a.score;
        case "change":
          return b.change_pct - a.change_pct;
        case "supply":
          return (b.supply_score ?? 0) - (a.supply_score ?? 0);
        default:
          return a.rank_no - b.rank_no;
      }
    });

    return result;
  }, [reports, query, sortKey]);

  return (
    <div className="space-y-4">
      <SeedAllocator reports={filtered} />

      {/* 검색 + 정렬 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="종목명·티커·섹터로 검색"
            className="w-full rounded-full bg-white px-11 py-3 text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 dark:bg-slate-900/60 dark:text-slate-100"
          />
        </div>
        <div className="flex items-center gap-1 rounded-full bg-slate-100 p-1 dark:bg-slate-800/60">
          {(
            [
              { k: "rank", label: "순위" },
              { k: "score", label: "점수" },
              { k: "supply", label: "수급" },
              { k: "change", label: "등락" },
            ] as { k: SortKey; label: string }[]
          ).map(({ k, label }) => (
            <button
              key={k}
              type="button"
              onClick={() => setSortKey(k)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-extrabold transition-colors ${
                sortKey === k
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 결과 */}
      <p className="text-xs font-bold text-slate-500 dark:text-slate-400">
        총 {filtered.length}개
      </p>

      {filtered.length === 0 ? (
        <div className="rounded-3xl bg-white p-12 text-center dark:bg-slate-900/60">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            검색 결과가 없습니다.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((r) => (
            <StockReportCard key={r.stock_code} report={r} date={date} />
          ))}
        </div>
      )}
    </div>
  );
}
