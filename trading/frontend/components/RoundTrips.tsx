import { won, wonExact, pnlClass } from "@/lib/format";
import type { RoundTrip, DayPlan, NameMap } from "@/types";

/** 전일 매수 → 당일 매도 라운드트립 목록: 종목별 매수가→매도가, 실현손익을 한 줄로.
 *  plans 를 주면 갭상승/갭하락 배지를 함께 표시한다(달력 상세용). */
export default function RoundTrips({
  trips,
  names,
  plans,
}: {
  trips: RoundTrip[];
  names: NameMap;
  plans?: DayPlan[];
}) {
  const nm = (c: string) => names[c] || c;
  const gapOf = (cd: string) => plans?.find((p) => p.stk_cd === cd)?.gap_dir;
  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {trips.map((t) => {
        const pct = t.buy_price > 0 ? ((t.sell_price - t.buy_price) / t.buy_price) * 100 : 0;
        const gap = gapOf(t.stk_cd);
        return (
          <li key={t.stk_cd} className="py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="truncate font-semibold">{nm(t.stk_cd)}</span>
                {gap && (
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                      gap === "up"
                        ? "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400"
                        : "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400"
                    }`}
                  >
                    {gap === "up" ? "갭상승" : "갭하락"}
                  </span>
                )}
              </span>
              <span className={`shrink-0 font-bold tabular-nums ${pnlClass(t.realized)}`}>
                {won(t.realized)}
                {t.buy_price > 0 && (
                  <span className="ml-1 text-xs font-medium">
                    ({pct >= 0 ? "+" : ""}
                    {pct.toFixed(1)}%)
                  </span>
                )}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-slate-400 tabular-nums">
              <span>매수 {wonExact(t.buy_price)}</span>
              <span className="text-slate-300 dark:text-slate-600">→</span>
              <span>매도 {wonExact(t.sell_price)}</span>
              <span className="text-slate-300 dark:text-slate-600">·</span>
              <span>{t.sell_qty}주</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
