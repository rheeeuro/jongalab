import Link from "next/link";
import { Crown } from "lucide-react";
import { StockReport } from "@/types";

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white dark:bg-slate-600",
  D: "bg-slate-300 text-white dark:bg-slate-700",
};

type GapLine = { label: "NXT" | "KRX"; pct: number };

function resolveGapLines(r: StockReport): GapLine[] {
  // 텔레그램 포맷과 동일: NXT+KRX 둘 다 있으면 KRX는 NXT→KRX 장중 델타
  const hasNxt = typeof r.gap_nxt_pct === "number";
  const hasKrx = typeof r.gap_krx_pct === "number";
  const lines: GapLine[] = [];
  if (hasNxt) lines.push({ label: "NXT", pct: r.gap_nxt_pct! });
  if (hasKrx) {
    if (
      hasNxt &&
      r.gap_nxt_price != null &&
      r.gap_krx_price != null &&
      r.gap_nxt_price > 0
    ) {
      lines.push({
        label: "KRX",
        pct: ((r.gap_krx_price - r.gap_nxt_price) / r.gap_nxt_price) * 100,
      });
    } else {
      lines.push({ label: "KRX", pct: r.gap_krx_pct! });
    }
  }
  return lines;
}

export function finalGapPct(r: StockReport): number | null {
  // 리포트가 → 최종(KRX 우선, NXT 폴백) 누적 등락 기준
  if (typeof r.gap_krx_pct === "number") return r.gap_krx_pct;
  if (typeof r.gap_nxt_pct === "number") return r.gap_nxt_pct;
  return null;
}

function pctColor(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-500";
}

export function StockReportCard({
  report: r,
  date,
  displayRank,
}: {
  report: StockReport;
  date: string;
  displayRank?: number;
}) {
  const isUp = r.change_pct > 0;
  const isDown = r.change_pct < 0;
  const gapLines = resolveGapLines(r);
  const totalPct = finalGapPct(r);
  const gapTone =
    totalPct === null
      ? "bg-white dark:bg-slate-900/60"
      : totalPct > 0
        ? "bg-rose-50/30 ring-1 ring-rose-200/40 dark:bg-rose-950/20 dark:ring-rose-900/40"
        : totalPct < 0
          ? "bg-blue-50/30 ring-1 ring-blue-200/40 dark:bg-blue-950/20 dark:ring-blue-900/40"
          : "bg-white dark:bg-slate-900/60";

  return (
    <Link
      href={`/reports/${date}/${r.stock_code}`}
      className={`group rounded-2xl p-4 transition-all hover:-translate-y-0.5 hover:shadow-md ${gapTone}`}
    >
      {/* 상단: 순위 + 종목명 + 플래그 / 우측: 현재가 + 등락율 */}
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-xs font-black text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              {displayRank ?? r.rank_no}
            </span>
            <span className="min-w-0 truncate font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-400">
              {r.stock_name}
            </span>
            {r.is_leader && (
              <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
            )}
            {r.is_theme_stock && (
              <span className="shrink-0 rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] font-extrabold text-orange-600 dark:bg-orange-950/40 dark:text-orange-400">
                테마
              </span>
            )}
          </div>
          <p className="mt-1.5 truncate text-xs text-slate-500 dark:text-slate-400">
            {r.sector || "기타"} ·{" "}
            {(r.trading_value / 1e8).toLocaleString("ko-KR", {
              maximumFractionDigits: 0,
            })}
            억
          </p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <div className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
            {r.current_price.toLocaleString("ko-KR")}
            <span className="ml-0.5 text-[10px] font-bold text-slate-400">
              원
            </span>
          </div>
          <div
            className={`text-xs font-extrabold ${
              isUp
                ? "text-rose-600 dark:text-rose-400"
                : isDown
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-slate-500"
            }`}
          >
            {isUp ? "+" : ""}
            {r.change_pct.toFixed(1)}%
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-1.5">
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
              GRADE_TONE[r.supply_grade] || GRADE_TONE.D
            }`}
          >
            수급{r.supply_grade}
          </span>
          {(r.news_count ?? 0) > 0 && (
            <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
              뉴스 {r.news_count}
            </span>
          )}
        </div>
        <div className="text-right tabular-nums">
          <span className="text-base font-extrabold text-indigo-600 dark:text-indigo-400">
            {r.score.toFixed(0)}
          </span>
          <span className="text-xs text-slate-400">점</span>
        </div>
      </div>

      {/* 다음날 아침 갭 결과 — NXT, KRX, 최종 한 줄 */}
      {(gapLines.length > 0 || totalPct !== null) && (
        <div
          className={`mt-3 flex flex-wrap items-baseline gap-x-2.5 gap-y-1 rounded-lg px-2.5 py-1.5 text-[11px] font-bold ${
            totalPct === null
              ? "bg-slate-50 dark:bg-slate-800/60"
              : totalPct > 0
                ? "bg-rose-100/60 dark:bg-rose-950/40"
                : totalPct < 0
                  ? "bg-blue-100/60 dark:bg-blue-950/40"
                  : "bg-slate-50 dark:bg-slate-800/60"
          }`}
        >
          {gapLines.map((g) => (
            <span
              key={g.label}
              className="inline-flex items-baseline gap-1"
            >
              <span className="text-slate-500 dark:text-slate-400">
                {g.label}
              </span>
              <span className={`tabular-nums ${pctColor(g.pct)}`}>
                {g.pct > 0 ? "+" : ""}
                {g.pct.toFixed(2)}%
              </span>
            </span>
          ))}
          {totalPct !== null && (
            <span className="ml-auto inline-flex items-baseline gap-1">
              <span className="text-slate-500 dark:text-slate-400">최종</span>
              <span className={`tabular-nums ${pctColor(totalPct)}`}>
                {totalPct > 0 ? "+" : ""}
                {totalPct.toFixed(2)}%
              </span>
            </span>
          )}
        </div>
      )}
    </Link>
  );
}
