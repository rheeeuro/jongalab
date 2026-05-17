import { SectorReport, MentionStats } from "@/types";
import { apiFetch } from "@/lib/api";
import { Layers, Flame, TrendingUp, TrendingDown } from "lucide-react";
import Link from "next/link";

async function getLatestSectorReport(): Promise<{
  date: string;
  sectors: SectorReport[];
}> {
  const dates = await apiFetch<string[]>(`/api/stock-report/dates?limit=1`, []);
  if (!dates.length) return { date: "", sectors: [] };
  const sectors = await apiFetch<SectorReport[]>(
    `/api/sector-report/${dates[0]}`,
    [],
  );
  return { date: dates[0], sectors };
}

async function getMentionStats(market: string): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats?market=${market}`,
    null,
  );
  return res?.success ? res.data : null;
}

export const dynamic = "force-dynamic";

export default async function SectorsPage(props: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await props.searchParams;
  const market = (params?.market as string) || "ALL";

  const [{ date, sectors }, mentionStats] = await Promise.all([
    getLatestSectorReport(),
    getMentionStats(market),
  ]);

  // 섹터별 언급 수 맵
  const mentionMap = new Map<string, number>();
  if (mentionStats?.sectors) {
    for (const s of mentionStats.sectors) {
      mentionMap.set(s.sector, s.mention_count);
    }
  }

  // 시장 등락률 기준 정렬 (이미 rank_no로 정렬되어 있다고 가정하지만, 한번 더)
  const sorted = [...sectors].sort((a, b) => a.rank_no - b.rank_no);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <Layers className="h-4 w-4 text-indigo-500" />
            <span>섹터 트렌드</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            오늘의
            <br />
            리딩 섹터.
          </h1>
          {date && (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
              기준일: <span className="font-bold">{date}</span> · 총{" "}
              <span className="font-bold">{sorted.length}</span>개 섹터
            </p>
          )}
        </header>

        {/* 언급 트렌드 요약 */}
        {mentionStats && mentionStats.sectors?.length > 0 && (
          <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
              <Flame className="h-5 w-5 text-orange-500" />
              가장 많이 언급된 섹터 (24시간)
            </h2>
            <div className="flex flex-wrap gap-2">
              {mentionStats.sectors.slice(0, 8).map((s) => (
                <span
                  key={s.sector}
                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-bold dark:bg-slate-800"
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
          </section>
        )}

        {/* 섹터 그리드 */}
        {sorted.length > 0 ? (
          <section>
            <h2 className="mb-4 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
              섹터 랭킹
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sorted.map((s) => (
                <SectorCard
                  key={s.thema_grp_cd}
                  sector={s}
                  mentionCount={mentionMap.get(s.thema_nm)}
                />
              ))}
            </div>
          </section>
        ) : (
          <div className="rounded-3xl bg-white p-12 text-center dark:bg-slate-900/60">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              아직 섹터 리포트가 준비되지 않았어요.
            </p>
          </div>
        )}
      </div>
    </main>
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
