"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { StockReport } from "@/types";
import { Search, Crown, TrendingUp, TrendingDown } from "lucide-react";

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white",
  D: "bg-slate-300 text-white",
};

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
            <StockRow key={r.stock_code} report={r} date={date} />
          ))}
        </div>
      )}
    </div>
  );
}

function StockRow({ report: r, date }: { report: StockReport; date: string }) {
  const isUp = r.change_pct > 0;
  const isDown = r.change_pct < 0;
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";

  return (
    <Link
      href={`/reports/${date}/${r.stock_code}`}
      className="group rounded-2xl bg-white p-4 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60"
    >
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-xs font-black text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
          {r.rank_no}
        </span>
        <span className="min-w-0 truncate font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-400">
          {r.stock_name}
        </span>
        {r.is_leader && (
          <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
        )}
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
            GRADE_TONE[r.supply_grade] || GRADE_TONE.D
          }`}
        >
          {r.supply_grade}
        </span>
      </div>

      <p className="mt-1.5 truncate text-xs text-slate-500 dark:text-slate-400">
        {r.sector || "기타"} · {r.stock_code}
      </p>

      <div className="mt-3 flex items-center justify-between">
        <span
          className={`flex items-center gap-1 text-sm font-extrabold tabular-nums ${changeColor}`}
        >
          {Icon && <Icon className="h-3.5 w-3.5" />}
          {isUp ? "+" : ""}
          {r.change_pct.toFixed(1)}%
        </span>
        <div className="text-right tabular-nums">
          <span className="text-base font-extrabold text-indigo-600 dark:text-indigo-400">
            {r.score.toFixed(0)}
          </span>
          <span className="text-xs text-slate-400">점</span>
        </div>
      </div>
    </Link>
  );
}
