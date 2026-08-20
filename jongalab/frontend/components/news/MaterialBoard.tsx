"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Newspaper, Search, SlidersHorizontal } from "lucide-react";
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
 * 판정 방식 안내(접이식)를 목록 바로 위에 두는 이유도 같다 — 등급이 보이는 자리에서 읽혀야 한다.
 *
 * 모바일 우선: 검색 → 정렬(전체 폭) → 등급 칩 → 유형 칩(접힘) 순으로 쌓고, 목록은 1열 행.
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
  const [showCatalyst, setShowCatalyst] = useState(false);

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
      <div className="mb-2 flex items-end justify-between gap-2">
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

      {/* 등급 안내·면책 — 카드 없이 한 줄로, 등급 칩이 보이는 자리 바로 위에 둔다.
          닫힌 상태에서도 '미검증'이 보이게 남긴다(details/summary, CSS-only). */}
      <details className="mb-3">
        <summary className="cursor-pointer list-none text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300">
          ⚠️ 재료 등급은 아직 검증되지 않은 실험이에요 — 어떻게 정하나요?
        </summary>
        <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          후보 종목에 뉴스가 있으면 AI가 그 내용을 읽고 <b>이 이야기가 더 이어질지</b> 판단해요.
          앞으로 남은 일정이 있고 결과가 아직 안 나왔으면 &lsquo;연속&rsquo;, 결과가 이미 다
          나오고 남은 일정도 없으면 &lsquo;소진&rsquo;이에요. 무엇 때문에 움직였는지 딱 집을 수
          없으면 억지로 고르지 않고 비워 둬요.
          <br />
          <span className="font-bold text-slate-400 dark:text-slate-500">
            이 등급은 &ldquo;사라는 신호&rdquo;가 아니고, 실제 매매에도 쓰지 않아요(성적만 기록하고 있어요).
          </span>
        </p>
      </details>

      {/* ── 컨트롤 ── */}
      <div className="space-y-2">
        {/* 375px 에서 정렬 select 와 검색창을 한 줄에 두면 검색창이 눌린다 — sm 부터 한 줄. */}
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="relative flex min-w-0 flex-1 items-center">
            <Search className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="종목·섹터 검색"
              className="h-10 w-full rounded-full bg-white pl-9 pr-3 text-sm font-medium text-slate-900 outline-none ring-1 ring-transparent transition focus:ring-emerald-400 dark:bg-slate-900/60 dark:text-slate-100"
            />
          </label>
          <label className="relative flex items-center sm:shrink-0">
            <SlidersHorizontal className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              aria-label="정렬"
              className="h-10 w-full appearance-none rounded-full bg-white pl-9 pr-3 text-sm font-bold text-slate-700 outline-none ring-1 ring-transparent transition focus:ring-emerald-400 sm:w-auto dark:bg-slate-900/60 dark:text-slate-200"
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
          {/* 유형 칩은 축이 달라서 같은 줄에 이어 붙이면 모바일 가로 스크롤에 묻힌다 — 접어 둔다. */}
          {catalystChips.length > 0 && (
            <Chip
              active={showCatalyst || catalyst !== null}
              onClick={() => {
                setShowCatalyst((v) => !v);
                if (catalyst !== null) setCatalyst(null);
              }}
              label={catalyst ?? "유형"}
              count={catalyst ? (catalystChips.find(([n]) => n === catalyst)?.[1] ?? 0) : catalystChips.length}
            />
          )}
        </div>

        {showCatalyst && catalystChips.length > 0 && (
          <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
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
        )}
      </div>

      {/* ── 목록 ── */}
      <div className="mt-3 overflow-hidden rounded-2xl bg-white dark:bg-slate-900/60">
        {filtered.length === 0 ? (
          <p className="p-6 text-center text-sm font-medium text-slate-400">
            조건에 맞는 종목이 없어요.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {filtered.map((r) => (
              <li key={r.stock_code} className="flex items-stretch">
                <MaterialRow row={r} date={date} />
                {/* 이 종목 기사만 보기 — 아래 헤드라인 스트림을 서버에서 필터해 준다. */}
                <Link
                  href={`/news?date=${date}&ns=${r.stock_code}#headlines`}
                  aria-label={`${r.stock_name} 기사만 보기`}
                  title="이 종목 기사만 보기"
                  className="flex w-11 shrink-0 items-center justify-center border-l border-slate-100 text-slate-300 transition-colors hover:bg-slate-50 hover:text-emerald-600 dark:border-slate-800 dark:text-slate-600 dark:hover:bg-slate-800/60 dark:hover:text-emerald-400"
                >
                  <Newspaper className="h-4 w-4" />
                </Link>
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
  // ⚠️ `news_count` 는 **카운트 게이트(텔레그램) 값**이다. 네이버에만 있는 종목은 0 이 나오는데
  // (실측 2026-08-20: 18행 중 6행), 이 행들은 라벨이 있어서 목록에 오른 종목이다. 0 을 그대로
  // 쓰면 "재료 목록에 있는데 뉴스 없음"이라고 말하는 셈이라 뉴스량 표기 자체를 뺀다.
  const heat = row.news_count > 0 ? newsHeatLabel(row.news_count, row.news_prior_avg) : null;

  return (
    <Link
      href={`/reports/${date}/${row.stock_code}`}
      className="block min-w-0 flex-1 px-4 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
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

      {/* 강조(뉴스 N배)를 근거(41건 · 평소 10건/일)보다 **앞에** 둔다 — 뒤에 두면 회색 잔글씨
          뒤에 붙어 강조가 되지 않는다. */}
      <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
        {row.sector && <span className="truncate">{row.sector}</span>}
        {heat && (
          <>
            {row.sector && <span aria-hidden>·</span>}
            <span
              className={
                heat.emphasis ? "font-bold text-emerald-600 dark:text-emerald-400" : ""
              }
            >
              {heat.headline}
            </span>
            <span aria-hidden>·</span>
            <span className="tabular-nums">{heat.detail}</span>
          </>
        )}
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
