import { StockReport, SectorReport } from "@/types";
import { DailySummaryCard } from "@/components/DailySummaryCard";
import { StockReportCard, finalGapPct } from "@/components/StockReportCard";
import { apiFetch } from "@/lib/api";
import { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, FileText, Layers, BarChart3 } from "lucide-react";

function fetchOptions(date: string): RequestInit {
  const today = new Date().toLocaleDateString("en-CA");
  return date >= today
    ? { cache: "no-store" }
    : ({ next: { revalidate: 600 } } as RequestInit);
}

async function getStockReports(date: string): Promise<StockReport[]> {
  return apiFetch(`/api/stock-report/${date}`, [], fetchOptions(date));
}

async function getSectorReports(date: string): Promise<SectorReport[]> {
  return apiFetch(`/api/sector-report/${date}`, [], fetchOptions(date));
}

export async function generateMetadata({
  params,
}: {
  params: { date: string };
}): Promise<Metadata> {
  const resolvedParams = await params;
  const stockReports = await getStockReports(resolvedParams.date);
  const topPick = stockReports[0] ?? null;

  if (!topPick) {
    return { title: "리포트를 찾을 수 없습니다" };
  }

  const title = `[${resolvedParams.date}] 투자 리포트`;
  const description = `매수 추천: ${topPick.stock_name} (${topPick.reason}). AI 주식 에이전트의 일일 브리핑을 확인하세요.`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `https://jongalab.com/reports/${resolvedParams.date}`,
      siteName: "종가랩",
      type: "article",
    },
  };
}

function gapWinRate(reports: StockReport[]) {
  const top10 = reports.filter((r) => r.rank_no >= 1 && r.rank_no <= 10);
  let wins = 0, losses = 0, flats = 0;
  for (const r of top10) {
    const pct = finalGapPct(r);
    if (pct === null) continue;
    if (pct > 0) wins++;
    else if (pct < 0) losses++;
    else flats++;
  }
  const total = wins + losses + flats;
  return { wins, losses, flats, total };
}

export default async function ReportPage({
  params,
}: {
  params: { date: string };
}) {
  const resolvedParams = await params;
  const date = resolvedParams.date;

  const [stockReports, sectorReports] = await Promise.all([
    getStockReports(date),
    getSectorReports(date),
  ]);
  const topPick = stockReports[0] ?? null;

  if (stockReports.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="text-center">
          <p className="text-sm font-medium text-slate-400">
            해당 날짜의 리포트가 없습니다.
          </p>
          <p className="mt-2 text-2xl font-extrabold text-slate-900 dark:text-slate-100">
            {date}
          </p>
          <Link
            href="/reports"
            className="mt-6 inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-sm font-bold text-white dark:bg-white dark:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            아카이브로
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-10">
        <Link
          href="/reports"
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          리포트 아카이브
        </Link>

        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <FileText className="h-4 w-4 text-indigo-500" />
            <span>AI 투자 리포트</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            {date}
          </h1>
        </header>

        {/* 오늘의 추천 종목 카드 (종목 랭킹 1위) */}
        {topPick && <DailySummaryCard pick={topPick} disableLink />}

        {/* 주도 섹터 */}
        {sectorReports.length > 0 && (
          <section>
            <SectionHeader
              icon={<Layers className="h-5 w-5 text-violet-500" />}
              title="주도 섹터"
              count={`TOP ${sectorReports.length}`}
              timestamp={sectorReports[0]?.created_at}
            />

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {sectorReports.map((s) => {
                const isUp = s.flu_rt > 0;
                const isDown = s.flu_rt < 0;

                return (
                  <div
                    key={s.thema_grp_cd}
                    className="rounded-2xl bg-white p-4 dark:bg-slate-900/60 sm:p-5"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-xs font-black text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
                        {s.rank_no}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-extrabold text-slate-900 dark:text-slate-100">
                          {s.thema_nm}
                        </p>
                        <p className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                          {s.stk_num}종목 ·{" "}
                          <span className="text-rose-500">{s.rising_stk_num}↑</span>{" "}
                          <span className="text-blue-500">{s.fall_stk_num}↓</span>
                        </p>
                      </div>
                      <div className="text-right">
                        <p
                          className={`text-base font-extrabold tabular-nums ${
                            isUp
                              ? "text-rose-600 dark:text-rose-400"
                              : isDown
                                ? "text-blue-600 dark:text-blue-400"
                                : "text-slate-500"
                          }`}
                        >
                          {isUp ? "+" : ""}
                          {s.flu_rt.toFixed(2)}%
                        </p>
                        <p className="text-[10px] font-medium text-slate-400">
                          기간{" "}
                          <span
                            className={
                              s.dt_prft_rt > 0
                                ? "text-rose-500"
                                : s.dt_prft_rt < 0
                                  ? "text-blue-500"
                                  : ""
                            }
                          >
                            {s.dt_prft_rt > 0 ? "+" : ""}
                            {s.dt_prft_rt.toFixed(1)}%
                          </span>
                        </p>
                      </div>
                    </div>

                    {/* 구성종목 */}
                    <div className="mt-3 flex flex-wrap gap-1">
                      {s.stocks.slice(0, 6).map((stk) => {
                        const stkUp = parseFloat(stk.flu_rt) > 0;
                        const stkDown = parseFloat(stk.flu_rt) < 0;
                        return (
                          <span
                            key={stk.stk_cd}
                            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium dark:bg-slate-800"
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
                          </span>
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
              })}
            </div>
          </section>
        )}

        {/* 종목 일간 리포트 */}
        {stockReports.length > 0 && (() => {
          const gapStat = gapWinRate(stockReports);
          return (
          <section>
            <SectionHeader
              icon={<BarChart3 className="h-5 w-5 text-indigo-500" />}
              title="종목 수급 분석"
              count={`${stockReports.length}개 종목`}
              timestamp={stockReports[0]?.created_at}
            />

            {/* 갭 체크 결과 요약 (Top 10) */}
            {gapStat.total > 0 && (
              <div className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-amber-50 px-4 py-3 text-sm font-bold text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                <span className="text-base">🌅</span>
                <span>다음날 아침 갭 체크 (Top 10):</span>
                <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-extrabold text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
                  {gapStat.wins}승
                </span>
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-extrabold text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
                  {gapStat.losses}패
                </span>
                {gapStat.flats > 0 && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-extrabold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    보합 {gapStat.flats}
                  </span>
                )}
                <span className="ml-auto text-xs font-extrabold tabular-nums">
                  승률 {((gapStat.wins / gapStat.total) * 100).toFixed(0)}%
                </span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {stockReports.map((r) => (
                <StockReportCard key={r.stock_code} report={r} date={date} />
              ))}
            </div>
          </section>
          );
        })()}

        {/* AI 코멘트 */}
        {stockReports.length > 0 && (
          <div className="rounded-3xl bg-gradient-to-br from-indigo-50 to-violet-50 p-6 dark:from-indigo-950/30 dark:to-violet-950/30">
            <h2 className="mb-2 text-base font-extrabold text-slate-900 dark:text-slate-100">
              🤖 AI 코멘트
            </h2>
            <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
              오늘 수집된 다양한 유튜브 및 텔레그램 데이터를 종합한 결과입니다.
              투자의 참고 자료로만 활용하시기 바랍니다.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

function SectionHeader({
  icon,
  title,
  count,
  timestamp,
}: {
  icon: React.ReactNode;
  title: string;
  count?: string;
  timestamp?: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
      <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
        {icon}
        {title}
        {count && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {count}
          </span>
        )}
      </h2>
      {timestamp && (
        <span className="text-xs text-slate-400">
          {new Date(timestamp).toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "Asia/Seoul",
          })}{" "}
          기준
        </span>
      )}
    </div>
  );
}
