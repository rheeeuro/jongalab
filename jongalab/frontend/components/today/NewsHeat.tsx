import Link from "next/link";
import { Newspaper } from "lucide-react";
import { NewsHeatItem } from "@/types";

/**
 * 뉴스 재료 — 최근 24시간 속보 채널에서 언급이 많은 종목 랭킹.
 * 종가베팅 선정 여부와 무관하게 '지금 재료가 몰리는 종목'을 보여준다.
 * 모바일 우선: 세로 리스트, 넓은 화면에서 2열로 확장.
 */
export function NewsHeat({ items }: { items: NewsHeatItem[] }) {
  if (!items?.length) return null;

  const max = Math.max(...items.map((i) => i.mention_count), 1);

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          <Newspaper className="h-5 w-5 text-emerald-500" />
          뉴스 재료
        </h2>
        <span className="text-xs font-bold text-slate-400">최근 24시간</span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((it, idx) => (
          <Link
            key={it.ticker}
            href={`/stocks/${it.ticker}`}
            className="group flex items-center gap-3 rounded-2xl bg-white p-3 transition-colors hover:bg-slate-50 dark:bg-slate-900/60 dark:hover:bg-slate-800/60"
          >
            <span className="w-5 shrink-0 text-center text-sm font-bold tabular-nums text-slate-400">
              {idx + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-bold text-slate-800 dark:text-slate-200">
                  {it.company_name || it.ticker}
                </span>
                <span className="shrink-0 text-sm font-extrabold tabular-nums text-emerald-600 dark:text-emerald-400">
                  {it.mention_count}건
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-emerald-500 dark:bg-emerald-400"
                  style={{ width: `${(it.mention_count / max) * 100}%` }}
                />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
