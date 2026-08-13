"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, SlidersHorizontal } from "lucide-react";
import { NewsMaterialRow } from "@/types";
import { MaterialBadge, materialAxisLabels } from "@/components/MaterialBadge";
import { newsHeatLabel, newsSurprise } from "@/lib/news";

/**
 * 종목별 재료 목록 — **하나의 목록 + 필터**.
 *
 * 등급으로 미리 갈라 놓으면 절반 이상이 '판정 보류·중립'으로 떨어져 가장 큰 그룹이 "판정 못 함"이
 * 되고, 사용자가 원하는 축(뉴스가 많이 뜬 순 / 많이 오른 순 / 실적 재료만)으로는 볼 수가 없다.
 * 그래서 그룹핑 대신 **필터·정렬**을 쓴다 — 기본은 뉴스가 많이 뜬 순이고, 등급은 칩으로 좁힌다.
 *
 * ⚠️ 지속성 라벨은 여전히 관찰 전용·미검증이다. 필터 칩으로 승격시킨 것이 아니라 축을 하나
 * 늘린 것뿐이므로, 등급 칩 색은 `MaterialBadge` 규칙대로 손익 방향색을 쓰지 않는다.
 *
 * 모바일 우선: 검색 → 가로 스크롤 칩 → 정렬 select 순으로 쌓고, 목록은 1열 행.
 */

type View = "all" | "selected" | "연속" | "소진" | "pending";
type Sort = "news" | "change" | "rank";

const SORT_LABEL: Record<Sort, string> = {
  news: "평소보다 뉴스 많은 순",
  change: "등락률 순",
  rank: "후보 순위 순",
};

function isPending(r: NewsMaterialRow): boolean {
  return r.news_durability !== "연속" && r.news_durability !== "소진";
}

export function MaterialBoard({
  rows,
  date,
}: {
  rows: NewsMaterialRow[];
  /** 카드 링크 대상 리포트 날짜 */
  date: string;
}) {
  const [view, setView] = useState<View>("all");
  const [catalyst, setCatalyst] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("news");
  const [q, setQ] = useState("");

  const viewChips = useMemo(
    () =>
      [
        { key: "all" as const, label: "전체", n: rows.length },
        { key: "selected" as const, label: "선정", n: rows.filter((r) => r.selected === 1).length },
        { key: "연속" as const, label: "이어지는 재료", n: rows.filter((r) => r.news_durability === "연속").length },
        { key: "소진" as const, label: "소진", n: rows.filter((r) => r.news_durability === "소진").length },
        { key: "pending" as const, label: "판정 보류", n: rows.filter(isPending).length },
      ].filter((c) => c.n > 0 || c.key === "all"),
    [rows],
  );

  const catalystChips = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) if (r.news_catalyst) m.set(r.news_catalyst, (m.get(r.news_catalyst) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter((r) => {
      if (view === "selected" && r.selected !== 1) return false;
      if (view === "연속" && r.news_durability !== "연속") return false;
      if (view === "소진" && r.news_durability !== "소진") return false;
      if (view === "pending" && !isPending(r)) return false;
      if (catalyst && r.news_catalyst !== catalyst) return false;
      if (needle) {
        const hay = `${r.stock_name} ${r.stock_code} ${r.sector ?? ""}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    return out.sort((a, b) => {
      if (sort === "change") return (b.change_pct ?? 0) - (a.change_pct ?? 0);
      if (sort === "rank") return a.rank_no - b.rank_no;
      return (
        newsSurprise(b.news_count, b.news_prior_avg) -
          newsSurprise(a.news_count, a.news_prior_avg) || b.news_count - a.news_count
      );
    });
  }, [rows, view, catalyst, sort, q]);

  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-2">
        <h2 className="text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-lg">
          종목별 재료
          <span className="ml-1.5 text-xs font-bold text-slate-400 tabular-nums">
            {filtered.length}
            {filtered.length !== rows.length && ` / ${rows.length}`}
          </span>
        </h2>
        <span className="shrink-0 text-[11px] font-medium text-slate-400">
          오늘 후보 종목 기준
        </span>
      </div>

      {/* ── 컨트롤 ── */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <label className="relative flex min-w-0 flex-1 items-center">
            <Search className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="종목·섹터 검색"
              className="h-10 w-full rounded-full bg-white pl-9 pr-3 text-sm font-medium text-slate-900 outline-none ring-1 ring-transparent transition focus:ring-emerald-400 dark:bg-slate-900/60 dark:text-slate-100"
            />
          </label>
          <label className="relative flex shrink-0 items-center">
            <SlidersHorizontal className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              aria-label="정렬"
              className="h-10 appearance-none rounded-full bg-white pl-9 pr-3 text-sm font-bold text-slate-700 outline-none ring-1 ring-transparent transition focus:ring-emerald-400 dark:bg-slate-900/60 dark:text-slate-200"
            >
              {(Object.keys(SORT_LABEL) as Sort[]).map((s) => (
                <option key={s} value={s}>
                  {SORT_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
          {viewChips.map((c) => (
            <Chip
              key={c.key}
              active={view === c.key}
              onClick={() => setView(c.key)}
              label={c.label}
              count={c.n}
            />
          ))}
          {catalystChips.length > 0 && (
            <span className="mx-1 shrink-0 self-center text-slate-200 dark:text-slate-700">|</span>
          )}
          {catalystChips.map(([name, n]) => (
            <Chip
              key={name}
              active={catalyst === name}
              onClick={() => setCatalyst(catalyst === name ? null : name)}
              label={name}
              count={n}
            />
          ))}
        </div>
      </div>

      {/* ── 목록 ── */}
      <div className="mt-3 overflow-hidden rounded-2xl bg-white dark:bg-slate-900/60">
        {filtered.length === 0 ? (
          <p className="p-6 text-center text-sm font-medium text-slate-400">
            조건에 맞는 종목이 없습니다.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {filtered.map((r) => (
              <li key={r.stock_code}>
                <MaterialRow row={r} date={date} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function Chip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold transition-colors ${
        active
          ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
          : "bg-white text-slate-500 hover:text-slate-900 dark:bg-slate-900/60 dark:text-slate-400 dark:hover:text-slate-100"
      }`}
    >
      {label}
      <span className={`ml-1 tabular-nums ${active ? "opacity-70" : "text-slate-400"}`}>
        {count}
      </span>
    </button>
  );
}

/** 재료 1행 — 종목·등급·유형 / 등락률 / 근거 수치 / 요약. 누르면 판정 근거가 있는 리포트 상세로. */
function MaterialRow({ row, date }: { row: NewsMaterialRow; date: string }) {
  const chg = row.change_pct ?? 0;
  const axes = materialAxisLabels(row);
  const heat = newsHeatLabel(row.news_count, row.news_prior_avg);

  return (
    <Link
      href={`/reports/${date}/${row.stock_code}`}
      className="block px-4 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
            {row.stock_name}
          </span>
          <MaterialBadge durability={row.news_durability} />
          {row.news_catalyst && (
            <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {row.news_catalyst}
            </span>
          )}
          {row.selected === 1 && (
            <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
              선정
            </span>
          )}
        </div>
        <span
          className={`shrink-0 text-sm font-extrabold tabular-nums ${
            chg > 0
              ? "text-red-500 dark:text-red-400"
              : chg < 0
                ? "text-blue-500 dark:text-blue-400"
                : "text-slate-400"
          }`}
        >
          {chg > 0 ? "+" : ""}
          {chg.toFixed(2)}%
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
        {row.sector && <span className="truncate">{row.sector}</span>}
        <span aria-hidden>·</span>
        <span className="tabular-nums">{heat.detail}</span>
        <span
          className={`tabular-nums ${
            heat.emphasis ? "font-bold text-emerald-600 dark:text-emerald-400" : ""
          }`}
        >
          {heat.headline}
        </span>
        {axes.map((t) => (
          <span key={t}>· {t}</span>
        ))}
      </div>

      {row.news_summary && (
        <p className="mt-1.5 line-clamp-2 break-words text-xs leading-relaxed text-slate-600 dark:text-slate-300">
          {row.news_summary}
        </p>
      )}
    </Link>
  );
}
