import Link from "next/link";
import { ChevronRight, Newspaper } from "lucide-react";
import { NewsHeatItem } from "@/types";

/** 뉴스가 몰린 종목 — 홈의 **압축본**이다(전체는 `/news`).
 *
 * 세로 목록인 이유: 데스크탑에서는 우측 사이드바(≈19rem) 안에 들어가고 모바일에서는
 * 픽 목록 아래에 오는데, 가로 스크롤 칩은 좁은 사이드바에서 읽히지 않는다.
 *
 * ⚠️ 상한: 5건 목록이다. 차트·필터를 붙이지 말 것 — 홈이 다시 종합 대시보드가 된다.
 */
export function NewsDigest({
  items,
  date,
}: {
  items: NewsHeatItem[];
  date: string;
}) {
  const top = items.slice(0, 5);
  if (!top.length) return null;

  return (
    <section className="rounded-2xl bg-white p-4 dark:bg-slate-900/60">
      <div className="flex items-center gap-1.5">
        <Newspaper className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
        <h2 className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
          뉴스가 몰린 종목
        </h2>
        <Link
          href={`/news?date=${date}`}
          className="ml-auto inline-flex shrink-0 items-center gap-0.5 text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
        >
          뉴스
          <ChevronRight className="h-3 w-3" />
        </Link>
      </div>

      <ul className="mt-1 divide-y divide-slate-100 dark:divide-slate-800/60">
        {top.map((n) => (
          <li key={n.ticker}>
            <Link
              href={`/stocks/${n.ticker}`}
              className="flex items-center justify-between gap-2 py-2 transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              <div className="min-w-0">
                <p className="flex items-center gap-1 truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
                  <span className="truncate">{n.company_name || n.ticker}</span>
                  {n.in_universe === 1 && (
                    <span className="shrink-0 rounded-full bg-indigo-100 px-1 text-[10px] font-extrabold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                      후보
                    </span>
                  )}
                </p>
                <p className="truncate text-[11px] font-medium text-slate-400 tabular-nums dark:text-slate-500">
                  기사 {n.mention_count}건
                </p>
              </div>
              {/* 배수(자기 기저 대비)를 쓴다 — 건수 정렬은 사실상 시총 랭킹이 된다 */}
              <span className="shrink-0 text-xs font-extrabold text-slate-500 tabular-nums dark:text-slate-400">
                평소의 {(n.surprise ?? 1).toFixed(1)}배
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
