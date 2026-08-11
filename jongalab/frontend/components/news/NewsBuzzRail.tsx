import Link from "next/link";
import { Flame } from "lucide-react";
import { NewsHeatItem } from "@/types";
import { MaterialBadge } from "@/components/MaterialBadge";
import { newsHeatLabel } from "@/lib/news";

/**
 * 뉴스가 몰린 종목 — **유니버스 밖 종목까지** 포함하는 유일한 자리.
 *
 * 재료 목록(`/api/news/materials`)은 그 날 후보 종목만 다룬다. 실측 2026-08-03 기준 뉴스가
 * 붙은 종목은 131개인데 후보와 겹친 건 7개뿐이라, 재료 목록만으로는 "오늘 뉴스판"의 5%만
 * 보인다. 그래서 이 랭킹이 나머지를 덮는다 — 후보인 종목은 배지로 구분해 두 목록의 관계를
 * 드러낸다(같은 종목이 위아래에 이유 없이 두 번 나오는 것처럼 보이지 않게).
 *
 * 정렬은 홈 카드와 같은 **자기 기저 대비 배수**다. 건수 정렬은 시총 랭킹이 되어 매일 같은
 * 대형주만 올라온다. 넓은 화면에서는 오른쪽 사이드 레일, 모바일에서는 목록 아래로 흐른다.
 */
export function NewsBuzzRail({ items }: { items: NewsHeatItem[] }) {
  if (!items?.length) return null;
  const max = Math.max(...items.map((i) => i.surprise ?? i.mention_count), 1);

  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-lg">
          <Flame className="h-4.5 w-4.5 text-emerald-500" />
          뉴스가 몰린 종목
        </h2>
        <span className="shrink-0 text-[11px] font-medium text-slate-400">평소 대비 뉴스량</span>
      </div>

      <ul className="overflow-hidden rounded-2xl bg-white dark:bg-slate-900/60">
        {items.map((it, idx) => {
          const surprise = it.surprise ?? it.mention_count;
          const label = newsHeatLabel(it.mention_count, it.prior_avg);
          return (
            <li key={it.ticker} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
              <Link
                href={`/stocks/${it.ticker}`}
                className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
              >
                <span className="w-4 shrink-0 text-center text-xs font-bold tabular-nums text-slate-300 dark:text-slate-600">
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-sm font-bold text-slate-800 dark:text-slate-200">
                        {it.company_name || it.ticker}
                      </span>
                      {it.in_universe === 1 && (
                        <span className="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          후보
                        </span>
                      )}
                      <MaterialBadge durability={it.durability} />
                    </span>
                    <span
                      className={`shrink-0 text-sm font-extrabold tabular-nums ${
                        label.emphasis
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-slate-400 dark:text-slate-500"
                      }`}
                    >
                      {label.headline}
                    </span>
                  </div>

                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-full rounded-full bg-emerald-500 dark:bg-emerald-400"
                      style={{ width: `${Math.min((surprise / max) * 100, 100)}%` }}
                    />
                  </div>

                  <p className="mt-1 truncate text-[11px] font-medium text-slate-400 dark:text-slate-500">
                    <span className="tabular-nums">{label.detail}</span>
                    {it.catalyst ? ` · ${it.catalyst}` : ""}
                  </p>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
