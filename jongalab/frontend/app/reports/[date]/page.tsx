import { SectorReport } from "@/types";
import { DateStepper, formatReportDate } from "@/components/pick/DateStepper";
import { PickList } from "@/components/pick/PickList";
import { SeedAllocator } from "@/components/pick/SeedAllocator";
import {
  apiFetch,
  getReportDates,
  getRuleMap,
  getStockReports,
} from "@/lib/api";
import { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, FileText, Layers } from "lucide-react";

function fetchOptions(date: string): RequestInit {
  const today = new Date().toLocaleDateString("en-CA");
  return date >= today
    ? { cache: "no-store" }
    : ({ next: { revalidate: 600 } } as RequestInit);
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

  // 제목 앞머리는 **검색 의도 키워드**, 날짜는 괄호로 뒤에 둔다 — 날짜를 앞세우면
  // "종목명 날짜 종가" 같은 시세 조회 쿼리에만 걸린다. 근거: docs/plan/seo/search-visibility.md
  const title = `종가베팅 추천 ${stockReports.length}종목 (${resolvedParams.date})`;
  const description = `${topPick.stock_name} 외 ${stockReports.length}종목을 종가베팅 후보로 고른 근거 — 수급·기술·재료 점수와 다음날 아침 실제 결과까지 공개합니다.`;

  return {
    title,
    description,
    alternates: { canonical: `/reports/${resolvedParams.date}` },
    openGraph: {
      title,
      description,
      url: `https://jongalab.com/reports/${resolvedParams.date}`,
      siteName: "종가랩",
      type: "article",
    },
  };
}

export default async function ReportPage({
  params,
}: {
  params: { date: string };
}) {
  const resolvedParams = await params;
  const date = resolvedParams.date;

  const [stockReports, sectorReports, dates, ruleMap] = await Promise.all([
    getStockReports(date),
    getSectorReports(date),
    getReportDates(120),
    getRuleMap(),
  ]);

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
            href="/record"
            className="mt-6 inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-sm font-bold text-white dark:bg-white dark:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            날짜별 성적으로
          </Link>
        </div>
      </main>
    );
  }

  const ruleCount = new Set(
    stockReports.flatMap((r) => (r.rule_names ?? "").split(",").filter(Boolean)),
  ).size;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-5 sm:px-6 sm:py-8">
        {/* 홈(랜딩)과 일부러 다른 헤더를 쓴다 — 이 화면의 축은 '추천'이 아니라 '그 날짜'다.
            날짜 이동·그날 섹터가 여기 있고, 최근 성적·시장 요약은 홈에만 있다. */}
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <FileText className="h-4 w-4 text-indigo-500" />
            <span>일간 리포트</span>
            <Link
              href="/record"
              className="ml-auto text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
            >
              달력으로 보기
            </Link>
          </div>
          <h1 className="mt-2 text-2xl font-black tracking-tight text-slate-900 sm:text-3xl dark:text-slate-100">
            {formatReportDate(date)} 추천{" "}
            <span className="text-indigo-600 tabular-nums dark:text-indigo-400">
              {stockReports.length}종목
            </span>
          </h1>
          <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
            {ruleCount > 0
              ? `검증된 규칙 ${ruleCount}개가 고른 종목과 다음날 아침 결과입니다.`
              : "종합 점수로 고른 종목과 다음날 아침 결과입니다."}
          </p>
          <div className="mt-3">
            <DateStepper date={date} dates={dates} />
          </div>
        </header>

        <PickList
          reports={stockReports}
          date={date}
          ruleMap={ruleMap}
          action={<SeedAllocator reports={stockReports} />}
        />

        {sectorReports.length > 0 && <SectorSection sectors={sectorReports} />}
      </div>
    </main>
  );
}

/** 그날의 주도 섹터 — 종목 선정의 배경 맥락이라 추천 목록 아래에 둔다. */
function SectorSection({ sectors }: { sectors: SectorReport[] }) {
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 sm:text-xl dark:text-slate-100">
        <Layers className="h-5 w-5 text-violet-500" />
        이 날의 주도 섹터
        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          TOP {sectors.length}
        </span>
      </h2>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {sectors.map((s) => {
          const isUp = s.flu_rt > 0;
          const isDown = s.flu_rt < 0;

          return (
            <div
              key={s.thema_grp_cd}
              className="rounded-2xl bg-white p-4 sm:p-5 dark:bg-slate-900/60"
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
  );
}
