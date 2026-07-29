import Link from "next/link";
import { ChevronRight, Newspaper } from "lucide-react";
import { NewsHeatItem } from "@/types";
import { MaterialBadge } from "@/components/MaterialBadge";

/**
 * 오늘 새로 뜬 재료 — 최근 24시간 뉴스가 **자기 평소보다 몰린** 종목.
 *
 * 정렬축을 언급 건수에서 `surprise`(건수 ÷ 직전 7일 일평균)로 바꿨다. 건수 랭킹은 사실상
 * 시총 랭킹이라(2026-07-29 실측: 하이닉스 95·현대차 57·삼성전자 43건이 상단 고정) 매일 같은
 * 대형주만 보여 카드가 정보를 주지 못했다. 배수로 재면 "평소 조용했는데 오늘 시끄러운 종목"이
 * 올라온다. 근거(건수·평소 대비)를 함께 보여줘 사용자가 값을 검증할 수 있게 한다.
 *
 * 모바일 우선: 세로 리스트, 한 항목 2줄(종목명+배수 / 근거·재료). 넓은 화면에서 2열.
 */
export function NewsHeat({
  items,
  showAllLink = true,
}: {
  items: NewsHeatItem[];
  /** 뉴스 탭에서는 자기 자신으로 가는 링크라 숨긴다 */
  showAllLink?: boolean;
}) {
  if (!items?.length) return null;

  const max = Math.max(...items.map((i) => i.surprise ?? i.mention_count), 1);

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          <Newspaper className="h-5 w-5 text-emerald-500" />
          오늘 새로 뜬 재료
        </h2>
        {showAllLink ? (
          <Link
            href="/news"
            className="flex shrink-0 items-center gap-0.5 text-xs font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300"
          >
            평소 대비 <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <span className="shrink-0 text-xs font-bold text-slate-400">평소 대비 배수</span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((it, idx) => {
          const surprise = it.surprise ?? it.mention_count;
          const prior = it.prior_avg ?? 0;
          return (
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
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate text-sm font-bold text-slate-800 dark:text-slate-200">
                      {it.company_name || it.ticker}
                    </span>
                    <MaterialBadge durability={it.durability} />
                  </span>
                  <span className="shrink-0 text-sm font-extrabold tabular-nums text-emerald-600 dark:text-emerald-400">
                    ×{surprise.toFixed(1)}
                  </span>
                </div>

                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full bg-emerald-500 dark:bg-emerald-400"
                    style={{ width: `${Math.min((surprise / max) * 100, 100)}%` }}
                  />
                </div>

                <div className="mt-1 flex items-center gap-1.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
                  <span className="tabular-nums">{it.mention_count}건</span>
                  <span aria-hidden>·</span>
                  <span className="tabular-nums">평소 {prior.toFixed(1)}건/일</span>
                  {it.catalyst && (
                    <>
                      <span aria-hidden>·</span>
                      <span className="truncate">{it.catalyst}</span>
                    </>
                  )}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
