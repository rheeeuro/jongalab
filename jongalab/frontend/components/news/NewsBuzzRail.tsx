import Link from "next/link";
import { Flame } from "lucide-react";
import { NewsHeatItem } from "@/types";
import { MaterialBadge } from "@/components/MaterialBadge";
import { newsHeatLabel } from "@/lib/news";

/**
 * 뉴스가 몰린 종목 — **유니버스 밖 종목까지** 포함하는 유일한 자리.
 *
 * 재료 목록(`/api/news/materials`)은 그 날 후보 종목만 다룬다. 뉴스가 붙은 종목 중 후보와
 * 겹치는 건 극히 일부라 재료 목록만으로는 "오늘 뉴스판"의 한 조각만 보인다. 그래서 이 랭킹이
 * 나머지를 덮는다 — 후보인 종목은 배지로 구분해 두 목록의 관계를 드러낸다(같은 종목이
 * 위아래에 이유 없이 두 번 나오는 것처럼 보이지 않게).
 *
 * **모집단은 배수로 걸러 정하고(평소보다 늘어난 종목만), 순서·막대는 건수로 매긴다.**
 * 호출부가 `min_count`·`min_surprise`·`sort=count` 로 지정한다 — 왜 이 조합인지는
 * docs/history/frontend-ui.md 2026-08-20 항목.
 *
 * 막대는 **건수 비율**이다. 배수 비율로 그리면 분모 하한 탓에 '첫 등장'(기저 0건) 종목의
 * 배수와 실제 배수가 같은 축에 섞여, 기사가 가장 많은 종목의 막대가 가장 짧아진다.
 *
 * 넓은 화면에서는 오른쪽 사이드 레일, 모바일에서는 재료 목록 바로 아래로 흐른다
 * (헤드라인 스트림 뒤에 두면 모바일에서 사실상 도달하지 못한다).
 */
export function NewsBuzzRail({
  items,
  date,
}: {
  items: NewsHeatItem[];
  /** 후보 종목의 링크 대상 리포트 날짜 (재료 목록과 같은 곳으로 보낸다) */
  date: string;
}) {
  if (!items?.length) return null;
  const max = Math.max(...items.map((i) => i.mention_count), 1);

  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-lg">
          <Flame className="h-4.5 w-4.5 text-emerald-500" />
          뉴스가 몰린 종목
        </h2>
        <span className="shrink-0 text-[11px] font-medium text-slate-400">
          평소보다 늘어난 종목만
        </span>
      </div>

      <ul className="overflow-hidden rounded-2xl bg-white dark:bg-slate-900/60">
        {items.map((it) => {
          const label = newsHeatLabel(it.mention_count, it.prior_avg);
          // 후보(유니버스) 종목은 판정 근거가 있는 리포트 상세로 — 재료 목록 행과 같은 목적지다.
          const href =
            it.in_universe === 1 ? `/reports/${date}/${it.ticker}` : `/stocks/${it.ticker}`;
          return (
            <li key={it.ticker} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
              <Link
                href={href}
                className="block px-3 py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
              >
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
                  <span className="shrink-0 text-sm font-extrabold tabular-nums text-slate-800 dark:text-slate-200">
                    {it.mention_count}
                    <span className="ml-0.5 text-[11px] font-bold text-slate-400">건</span>
                  </span>
                </div>

                <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full bg-emerald-500 dark:bg-emerald-400"
                    style={{ width: `${Math.min((it.mention_count / max) * 100, 100)}%` }}
                  />
                </div>

                <p className="mt-1 truncate text-[11px] font-medium text-slate-400 dark:text-slate-500">
                  <span
                    className={
                      label.emphasis ? "font-bold text-emerald-600 dark:text-emerald-400" : ""
                    }
                  >
                    {label.headline}
                  </span>
                  {it.prior_avg ? ` · 평소 ${it.prior_avg.toFixed(1)}건/일` : ""}
                  {it.catalyst ? ` · ${it.catalyst}` : ""}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
