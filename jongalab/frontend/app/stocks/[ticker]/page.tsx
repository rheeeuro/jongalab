import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  Activity,
  MessagesSquare,
  Sparkles,
} from "lucide-react";
import {
  ContentAnalysis,
  ContentMentionSummary,
  NewsMentionResponse,
  PaginatedResponse,
  StockCandle,
  StockProfile,
  StockReport,
} from "@/types";
import { CandlestickChart } from "@/components/CandlestickChart";
import { MaterialNews } from "@/components/stock/MaterialNews";
import { OpinionList } from "@/components/stock/OpinionList";
import { OpinionSummary } from "@/components/stock/OpinionSummary";
import { PickHistory } from "@/components/stock/PickHistory";
import { SupplyPanel } from "@/components/pick/SupplyPanel";
import { PageButton } from "@/components/ui/page-button";
import { apiFetch } from "@/lib/api";
import { formatWon, formatWonCompact, josa, morningResult } from "@/lib/report";
import { PANEL } from "@/lib/ui";

const NEWS_DAYS = 3;
// 관련성(제목 매칭)이 실측 20~50% 라 6줄을 채우려면 넉넉히 받아야 한다(50행 ≈ 12KB).
const NEWS_LIMIT = 50;
// 여론 목록은 6줄 — 데스크탑 2열에서 3행, 모바일에서 화면 한 장 반이다.
// 목록 자체가 목적인 화면(뉴스 탭 콘텐츠 뷰)은 12건이지만, 여기선 '어느 쪽인가'가 목적이다.
const CONTENT_PAGE = 6;
const CANDLE_DAYS = 60;

async function getProfile(ticker: string): Promise<StockProfile | null> {
  const data = await apiFetch<StockProfile | null>(`/api/stock-profile/${ticker}`, null);
  return data && !data.error ? data : null;
}

async function getCandles(ticker: string): Promise<StockCandle[]> {
  return apiFetch(`/api/stock-history/${ticker}?days=${CANDLE_DAYS}`, []);
}

async function getReports(ticker: string): Promise<StockReport[]> {
  return apiFetch(`/api/stock-report/history/${ticker}?limit=5`, []);
}

async function getNews(ticker: string): Promise<NewsMentionResponse> {
  return apiFetch<NewsMentionResponse>(
    `/api/news/${ticker}?days=${NEWS_DAYS}&limit=${NEWS_LIMIT}`,
    { success: false, data: [] },
  );
}

async function getOpinion(ticker: string): Promise<ContentMentionSummary | null> {
  const res = await apiFetch<{ success: boolean; data: ContentMentionSummary | null }>(
    `/api/contents/mention-summary?ticker=${ticker}&days=7`,
    { success: false, data: null },
  );
  return res.data ?? null;
}

async function getContents(
  ticker: string,
  page: number,
): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch<PaginatedResponse<ContentAnalysis>>(
    `/api/contents?ticker=${ticker}&page=${page}&limit=${CONTENT_PAGE}`,
    { success: false, data: [], pagination: null },
  );
}

/** 표시용 종목명 — 리포트에 실린 정식 이름이 1순위다.
 *  `ticker_dictionary` 의 이름은 콘텐츠 매칭용 별칭('하이닉스')이라 화면 제목으로 쓰면
 *  리포트 화면(SK하이닉스)과 이름이 갈린다. 그래서 리포트 → 키움 → 코드 순으로 고른다. */
function displayName(
  reports: StockReport[],
  profile: StockProfile | null,
  ticker: string,
): string {
  return reports[0]?.stock_name || profile?.name || ticker;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }>;
}): Promise<Metadata> {
  const { ticker } = await params;
  const code = decodeURIComponent(ticker).toUpperCase();
  const [profile, reports, opinion] = await Promise.all([
    getProfile(code),
    getReports(code),
    getOpinion(code),
  ]);
  const name = displayName(reports, profile, code);
  const mentions = opinion?.total ?? 0;

  // 리포트 이력도 콘텐츠 언급도 없으면 시세·차트뿐이라 색인에서 뺀다
  // (사이트맵도 같은 기준으로 리포트 있는 종목만 싣는다). 근거: docs/plan/seo/search-visibility.md
  const hasSubstance = reports.length > 0 || mentions > 0;

  // 날짜가 붙는 리포트 상세(`{종목명} 투자분석 - YYYY.MM.DD`)와 달리 여기는 **상시** 페이지다.
  // 제목에 날짜를 넣지 않아 종목 이름만으로 찾는 질의를 이 화면이 받는다.
  const description =
    reports.length > 0
      ? `${name}(${code}) 종목 분석이에요. 종가베팅 후보로 뽑힌 기록 ${reports.length}건과 그때 왜 뽑혔는지, 다음날 아침 결과·수급(기관·외국인 매수)·뉴스 재료를 한 화면에 모아 뒀어요.`
      : `${name}(${code}) 종목 분석이에요. 일봉 차트와 함께, 모아 온 뉴스와 유튜브·텔레그램에서 이 종목이 어떻게 언급됐는지 볼 수 있어요.`;

  return {
    title: `${name} 종목 분석`,
    description,
    alternates: { canonical: `/stocks/${code}` },
    ...(hasSubstance ? {} : { robots: { index: false, follow: true } }),
  };
}

export default async function StockDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { ticker } = await params;
  const sp = await searchParams;
  const code = decodeURIComponent(ticker).toUpperCase();
  const page = Number(sp.page) || 1;

  const [profile, candles, reports, news, opinion, contents] = await Promise.all([
    getProfile(code),
    getCandles(code),
    getReports(code),
    getNews(code),
    getOpinion(code),
    getContents(code, page),
  ]);

  const name = displayName(reports, profile, code);
  const latest = reports[0] ?? null;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" });
  const pickedToday = latest?.report_date === today ? latest : null;
  const newsItems = news.data ?? [];
  const contentItems = contents.data ?? [];
  const pagination = contents.pagination;
  const mentions = opinion?.total ?? 0;
  const lastValue = candles.length ? candles[candles.length - 1].value : 0;

  const hasSupply = Boolean(latest && (latest.supply_history ?? []).length > 0);
  const hasNews = newsItems.length > 0;
  const hasReports = reports.length > 0;
  const nothingCollected = !hasReports && !hasNews && mentions === 0;

  return (
    <main className="min-h-screen">
      {/* 세로 리듬은 섹션 간 gap 하나로 통일한다 — 카드 안쪽 여백은 `PANEL` 이 갖는다. */}
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6 sm:py-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          홈으로
        </Link>

        {/* 헤더 — 시세가 주역이다(서버에서 받아 그리므로 값이 나중에 끼어들며 줄이 밀리지 않는다).
            ⚠️ **값 하나짜리 카드를 만들지 않는다** — 시총·PER 같은 단일 값은 아래 `dl` 한 줄에 모은다.
            경위: docs/history/frontend-ui.md */}
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <Sparkles className="h-4 w-4 text-indigo-500" />
            <span>종목 집중 분석</span>
          </div>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
              {name}
            </h1>
            <span className="font-mono text-base font-bold text-slate-400">{code}</span>
            {latest?.sector && (
              <span className="text-sm font-bold text-slate-500 dark:text-slate-400">
                {latest.sector}
              </span>
            )}
          </div>

          {profile ? (
            <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-2xl font-black tabular-nums text-slate-900 sm:text-3xl dark:text-slate-100">
                {formatWon(profile.price)}원
              </span>
              <span
                className={`text-base font-extrabold tabular-nums ${
                  profile.change_percent > 0
                    ? "text-red-600 dark:text-red-400"
                    : profile.change_percent < 0
                      ? "text-blue-600 dark:text-blue-400"
                      : "text-slate-500 dark:text-slate-400"
                }`}
              >
                {profile.change > 0 ? "+" : ""}
                {formatWon(profile.change)}원 (
                {profile.change_percent > 0 ? "+" : ""}
                {profile.change_percent.toFixed(2)}%)
              </span>
            </div>
          ) : (
            <p className="mt-2 text-sm text-slate-400">시세를 가져오지 못했어요.</p>
          )}

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {pickedToday ? (
              <Link
                href={`/reports/${pickedToday.report_date}/${code}`}
                className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-extrabold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-900/60"
              >
                오늘 종가베팅 후보 {pickedToday.rank_no}위 · 리포트 보기 →
              </Link>
            ) : hasReports ? (
              <Link
                href={`/reports/${latest!.report_date}/${code}`}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-extrabold text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                마지막 선정 {latest!.report_date} · 리포트 보기 →
              </Link>
            ) : (
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-extrabold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                종가베팅 후보로 뽑힌 기록 없음
              </span>
            )}
            {mentions > 0 && (
              <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-extrabold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                최근 7일 콘텐츠 언급 {mentions}건
              </span>
            )}
          </div>

          {profile && (
            <dl className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1.5 text-xs">
              {[
                { label: "시가총액", value: formatWonCompact(profile.market_cap) },
                {
                  label: "거래대금",
                  value: lastValue > 0 ? `${formatWonCompact(lastValue)}원` : "-",
                },
                {
                  label: "PER",
                  value: profile.per > 0 ? profile.per.toFixed(1) : "-",
                },
                {
                  label: "PBR",
                  value: profile.pbr > 0 ? profile.pbr.toFixed(2) : "-",
                },
                {
                  label: "1년 최고 대비",
                  value: `${profile.high_1y_gap_pct.toFixed(1)}%`,
                  tone:
                    profile.high_1y_gap_pct > -5
                      ? "text-red-600 dark:text-red-400"
                      : undefined,
                },
                {
                  label: "외국인",
                  value: profile.foreign_rate > 0 ? `${profile.foreign_rate.toFixed(1)}%` : "-",
                },
              ].map(({ label, value, tone }) => (
                <div key={label} className="flex items-baseline gap-1">
                  <dt className="font-medium text-slate-400 dark:text-slate-500">
                    {label}
                  </dt>
                  <dd
                    className={`font-bold tabular-nums ${tone ?? "text-slate-700 dark:text-slate-200"}`}
                  >
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          <p className="mt-3 max-w-3xl text-sm leading-relaxed break-keep text-slate-500 dark:text-slate-400">
            {lede({ name, code, sector: latest?.sector ?? null, profile, reports, opinion })}
          </p>
        </header>

        {/* 데스크탑은 **짝이 고정된 2열 밴드**다 — `차트↔선정 이력` · `수급↔재료 뉴스`.
            ⚠️ 짝의 높이를 설계로 맞춘다: 차트(≈430px)↔이력(요약을 한 줄로 낸 뒤 ≈470px) ·
            수급(≈400px)↔뉴스(6줄 ≈500px). 뉴스를 20줄로 두면 옆 수급 카드 옆에 1,000px 짜리
            빈 칸이 생긴다(그게 이 화면이 '이상해' 보인 이유 중 하나다).
            짝 중 하나만 있으면 남은 쪽이 전체 폭을 쓴다(빈 절반은 '카드가 빠진 자리'로 보인다).
            모바일(<lg)은 1열이라 DOM 순서가 곧 화면 순서다: 차트 → 선정 이력 → 수급 → 뉴스 → 여론. */}
        <div className={hasReports ? "grid grid-cols-1 gap-4 lg:grid-cols-2" : undefined}>
          <section className={PANEL}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
              <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
                <Activity className="h-4.5 w-4.5 text-teal-600 dark:text-teal-300" />
                일봉 차트
              </h2>
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
                최근 {CANDLE_DAYS}거래일
              </span>
            </div>
            <div className="mt-3">
              <CandlestickChart
                data={candles}
                height={280}
                fit
                timeVisible={false}
              />
            </div>
            <p className="mt-2 text-[11px] break-keep text-slate-400 dark:text-slate-500">
              한 봉이 하루 — 오르면 <span className="font-bold text-red-500">빨강</span>, 내리면{" "}
              <span className="font-bold text-blue-500">파랑</span>, 아래 막대는 거래량이에요.
            </p>
          </section>

          {hasReports && <PickHistory reports={reports} />}
        </div>

        {(hasSupply || hasNews) && (
          <div
            className={
              hasSupply && hasNews
                ? "grid grid-cols-1 gap-4 md:grid-cols-2 md:items-start"
                : undefined
            }
          >
            {hasSupply && (
              <SupplyPanel
                history={latest!.supply_history ?? []}
                grade={latest!.supply_grade}
                score={latest!.supply_score}
                days={latest!.supply_days}
                note={`${latest!.report_date.slice(5).replace("-", ".")} 선정 기준`}
              />
            )}
            {hasNews && (
              <MaterialNews
                items={newsItems}
                days={news.days ?? NEWS_DAYS}
                stockName={name}
                stockCode={code}
              />
            )}
          </div>
        )}

        {mentions > 0 && (
          <section className={PANEL}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
              <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
                <MessagesSquare className="h-4.5 w-4.5 text-indigo-500" />
                콘텐츠 여론
              </h2>
            </div>

            {opinion && (
              <div className="mt-3">
                <OpinionSummary summary={opinion} />
              </div>
            )}

            {contentItems.length > 0 && (
              <div className="mt-3">
                <OpinionList items={contentItems} code={code} />
              </div>
            )}

            {pagination && pagination.total_pages > 1 && (
              <div className="flex items-center justify-center gap-3 pt-4">
                <PageButton
                  href={`/stocks/${code}?page=${pagination.current_page - 1}`}
                  disabled={!pagination.has_prev_page}
                  direction="prev"
                />
                <span className="rounded-full bg-slate-100 px-4 py-2 text-sm font-bold tabular-nums text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                  {pagination.current_page} / {pagination.total_pages}
                </span>
                <PageButton
                  href={`/stocks/${code}?page=${pagination.current_page + 1}`}
                  disabled={!pagination.has_next_page}
                  direction="next"
                />
              </div>
            )}
          </section>
        )}

        {/* 아무것도 수집되지 않은 종목 — 시세·차트는 위에 이미 있으므로 '없다'만 말하지 않고
            어디로 가면 되는지 함께 낸다. */}
        {nothingCollected && (
          <section className={`${PANEL} text-center`}>
            <p className="text-sm leading-relaxed break-keep text-slate-500 dark:text-slate-400">
              <strong className="text-slate-900 dark:text-slate-100">{name}</strong>
              은(는) 아직 종가베팅 후보로 뽑힌 적이 없고, 최근 뉴스·콘텐츠에서도 언급이 잡히지
              않았어요. 위 차트는 실시간으로 계속 갱신돼요.
            </p>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <Link
                href="/"
                className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:opacity-90 dark:bg-white dark:text-slate-900"
              >
                오늘의 추천 보기
              </Link>
              <Link
                href="/news"
                className="rounded-full bg-slate-100 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              >
                뉴스가 몰린 종목 보기
              </Link>
            </div>
          </section>
        )}

        <p className="pb-6 text-center text-xs break-keep text-slate-400">
          이 화면은 AI가 자동으로 모은 참고 자료예요. 이것만 보고 투자를 결정하면 안 돼요.
        </p>
      </div>
    </main>
  );
}

/** 리드 문단 — 검색 유입용 줄글. 타일이 숫자로 이미 낸 것을 되풀이하지 않고, **값이 있는 문장**만 쓴다
 *  (안내 문구는 문장 자리를 차지하고 정보를 주지 않는다).
 *  ① 무슨 종목인가 ② 우리가 몇 번 골랐고 아침 결과가 어땼나 ③ 콘텐츠 여론이 어느 쪽인가. */
function lede({
  name,
  code,
  sector,
  profile,
  reports,
  opinion,
}: {
  name: string;
  code: string;
  sector: string | null;
  profile: StockProfile | null;
  reports: StockReport[];
  opinion: ContentMentionSummary | null;
}): string {
  const parts: string[] = [];

  const cap = profile && profile.market_cap > 0 ? formatWonCompact(profile.market_cap) : null;
  parts.push(
    sector && cap
      ? `${name}(${code})${josa(name, "은", "는")} ${sector} 업종이고 시가총액은 ${cap} 규모예요.`
      : cap
        ? `${name}(${code})의 시가총액은 ${cap} 규모예요.`
        : `${name}(${code}) 종목 자료예요.`,
  );

  if (reports.length > 0) {
    const measured = reports
      .map((r) => morningResult(r)?.pct)
      .filter((v): v is number => typeof v === "number");
    const last = reports[0];
    const wins = measured.filter((v) => v > 0).length;
    parts.push(
      `종가랩은 최근 이 종목을 ${reports.length}번 종가베팅 후보로 골랐고, 가장 가까운 선정일은 ${last.report_date}(수급 ${last.supply_grade}등급)이에요.`,
    );
    if (measured.length > 0) {
      const avg = measured.reduce((a, b) => a + b, 0) / measured.length;
      parts.push(
        `아침 결과가 나온 ${measured.length}번 중 ${wins}번이 올랐고 평균은 ${avg > 0 ? "+" : ""}${avg.toFixed(2)}%예요.`,
      );
    }
  } else {
    parts.push("종가베팅 후보로 뽑힌 기록은 아직 없어요.");
  }

  if (opinion && opinion.total > 0) {
    const { 호재: good, 악재: bad } = opinion.stance;
    const called = good + bad + opinion.stance.중립;
    // 언급 **건수**는 헤더 칩과 아래 요약 스트립이 이미 낸다 — 여기선 방향만 말한다.
    parts.push(
      called > 0
        ? `최근 ${opinion.days}일 유튜브·텔레그램 콘텐츠에서는 이 종목을 호재로 본 의견이 ${good}건, 악재로 본 의견이 ${bad}건이었어요.`
        : `최근 ${opinion.days}일 유튜브·텔레그램 콘텐츠에서 ${opinion.total}번 언급됐어요.`,
    );
  }

  return parts.join(" ");
}
