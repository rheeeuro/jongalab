import Link from "next/link";
import { Flame, Layers, TrendingDown, TrendingUp } from "lucide-react";
import { MentionStats, SectorReport } from "@/types";

/** 섹터 랭킹 — 예전 `/sectors` 탭의 본문. 지수·일정과 같은 '시장 배경' 정보라
 * 별도 목적지 대신 시장 탭 안의 섹션으로 둔다. */
export function SectorBoard({
  sectors,
  date,
  mentionStats,
}: {
  sectors: SectorReport[];
  date: string;
  mentionStats: MentionStats | null;
}) {
  const sorted = [...sectors].sort((a, b) => a.rank_no - b.rank_no);

  const mentionMap = new Map<string, number>();
  for (const s of mentionStats?.sectors ?? []) {
    mentionMap.set(s.sector, s.mention_count);
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 sm:text-xl dark:text-slate-100">
          <Layers className="h-5 w-5 text-violet-500" />
          섹터 랭킹
        </h2>
        {date && (
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
            기준일 {date} · {sorted.length}개 섹터
          </span>
        )}
      </div>

      {/* 언급이 몰린 섹터 — 시세와 다른 축(콘텐츠 언급)이라 랭킹 위에 칩으로만 */}
      {(mentionStats?.sectors?.length ?? 0) > 0 && (
        <div className="rounded-2xl bg-white p-4 dark:bg-slate-900/60">
          <h3 className="mb-3 flex items-center gap-1.5 text-xs font-extrabold text-slate-500 dark:text-slate-400">
            <Flame className="h-4 w-4 text-orange-500" />
            가장 많이 언급된 섹터 (24시간)
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {mentionStats!.sectors.slice(0, 8).map((s) => (
              <span
                key={s.sector}
                className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold dark:bg-slate-800"
              >
                <span className="text-slate-800 dark:text-slate-200">
                  {s.sector}
                </span>
                <span className="rounded-full bg-white px-1.5 text-[10px] font-extrabold text-orange-600 dark:bg-slate-900 dark:text-orange-400">
                  {s.mention_count}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {sorted.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((s) => (
            <SectorCard
              key={s.thema_grp_cd}
              sector={s}
              mentionCount={mentionMap.get(s.thema_nm)}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-3xl bg-white p-10 text-center dark:bg-slate-900/60">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            아직 섹터 리포트가 준비되지 않았어요.
          </p>
        </div>
      )}
    </section>
  );
}

function SectorCard({
  sector: s,
  mentionCount,
}: {
  sector: SectorReport;
  mentionCount?: number;
}) {
  const isUp = s.flu_rt > 0;
  const isDown = s.flu_rt < 0;
  const tone = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : null;

  return (
    <div className="overflow-hidden rounded-2xl bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 text-sm font-black text-white">
          {s.rank_no}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-extrabold text-slate-900 dark:text-slate-100">
            {s.thema_nm}
          </p>
          <p className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {s.stk_num}종목 ·{" "}
            <span className="text-rose-500">{s.rising_stk_num}↑</span>{" "}
            <span className="text-blue-500">{s.fall_stk_num}↓</span>
          </p>
        </div>
        <div className={`text-right ${tone}`}>
          <p className="flex items-center justify-end gap-1 text-lg font-extrabold tabular-nums">
            {Icon && <Icon className="h-4 w-4" />}
            {isUp ? "+" : ""}
            {s.flu_rt.toFixed(2)}%
          </p>
          <p className="text-[10px] font-bold text-slate-400">
            기간 {s.dt_prft_rt > 0 ? "+" : ""}
            {s.dt_prft_rt.toFixed(1)}%
          </p>
        </div>
      </div>

      {mentionCount !== undefined && mentionCount > 0 && (
        <div className="mt-3 inline-flex items-center gap-1 rounded-full bg-orange-50 px-2 py-0.5 text-[11px] font-extrabold text-orange-600 dark:bg-orange-950/30 dark:text-orange-400">
          <Flame className="h-3 w-3" />
          언급 {mentionCount}건
        </div>
      )}

      {/* 구성종목 */}
      <div className="mt-3 flex flex-wrap gap-1">
        {s.stocks.slice(0, 6).map((stk) => {
          const stkUp = parseFloat(stk.flu_rt) > 0;
          const stkDown = parseFloat(stk.flu_rt) < 0;
          return (
            <Link
              key={stk.stk_cd}
              href={`/stocks/${stk.stk_cd}`}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium transition-colors hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
            >
              <span className="text-slate-700 dark:text-slate-300">
                {stk.stk_nm}
              </span>
              <span
                className={
                  stkUp
                    ? "text-rose-500"
                    : stkDown
                      ? "text-blue-500"
                      : "text-slate-400"
                }
              >
                {stkUp ? "+" : ""}
                {parseFloat(stk.flu_rt).toFixed(1)}%
              </span>
            </Link>
          );
        })}
        {s.stocks.length > 6 && (
          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-400 dark:bg-slate-800">
            +{s.stocks.length - 6}
          </span>
        )}
      </div>
    </div>
  );
}
