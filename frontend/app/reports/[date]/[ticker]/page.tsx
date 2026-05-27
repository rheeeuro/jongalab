import { StockReportDetail, SupplyHistoryItem } from "@/types";
import { StockPriceBadge } from "@/components/StockPriceBadge";
import { CandlestickChart } from "@/components/CandlestickChart";
import { apiFetch } from "@/lib/api";
import { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  TrendingUp,
  Building2,
  Crown,
  BarChart3,
  Activity,
  CheckCircle2,
  XCircle,
  Newspaper,
  ExternalLink,
  Youtube,
  MessageCircle,
  Sunrise,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FixedLossCalculator } from "@/components/FixedLossCalculator";

function fetchOptions(date: string): RequestInit {
  // 종가베팅 워커가 평일 30분 간격으로 daily_stock_report를 DELETE+INSERT 하므로
  // 오늘 날짜는 no-store, 과거 날짜는 10분 정도만 캐싱.
  const today = new Date().toLocaleDateString("en-CA");
  return date >= today
    ? { cache: "no-store" }
    : ({ next: { revalidate: 600 } } as RequestInit);
}

async function getReportDetail(
  date: string,
  ticker: string
): Promise<StockReportDetail | null> {
  return apiFetch(`/api/stock-report/${date}/${ticker}`, null, fetchOptions(date));
}

export async function generateMetadata({
  params,
}: {
  params: { date: string; ticker: string };
}): Promise<Metadata> {
  const resolvedParams = await params;
  const data = await getReportDetail(resolvedParams.date, resolvedParams.ticker);

  if (!data) {
    return { title: "리포트를 찾을 수 없습니다" };
  }

  const r = data.report;
  const title = `[${resolvedParams.date}] ${r.stock_name} 일간 리포트`;
  const description = `수급 ${r.supply_grade}(${r.supply_score?.toFixed(1) ?? 0}점) | 종합 ${r.score}점 | 기관 ${formatBillion(r.inst_net_buy)}억 | 외인 ${formatBillion(r.frgn_net_buy)}억`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `https://stock.rheeeuro.com/reports/${resolvedParams.date}/${resolvedParams.ticker}`,
      siteName: "주식 AI 에이전트",
      type: "article",
    },
  };
}

function formatBillion(val: number): string {
  const b = val / 1e8;
  return b >= 0 ? `+${b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}` : b.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

function formatTradingValue(val: number): string {
  const b = val / 1e8;
  return `${b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}`;
}

function formatMarketCap(val: number): string {
  if (val <= 0) return "-";
  const trillion = val / 1e12;
  if (trillion >= 1) {
    return `${trillion.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`;
  }
  const billion = val / 1e8;
  return `${billion.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억`;
}

const SUPPLY_GRADE_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  S: { label: "S (종가베팅 최우선)", color: "text-red-700 dark:text-red-400", bg: "bg-red-100 dark:bg-red-900/40" },
  A: { label: "A (관심권)", color: "text-orange-700 dark:text-orange-400", bg: "bg-orange-100 dark:bg-orange-900/40" },
  B: { label: "B (조건부 관찰)", color: "text-yellow-700 dark:text-yellow-400", bg: "bg-yellow-100 dark:bg-yellow-900/40" },
  C: { label: "C (수급 약함)", color: "text-slate-600 dark:text-slate-400", bg: "bg-slate-100 dark:bg-slate-800" },
  D: { label: "D (제외)", color: "text-slate-500 dark:text-slate-500", bg: "bg-slate-50 dark:bg-slate-900" },
};

function SupplyGradeBadge({ grade, score }: { grade: string; score?: number }) {
  const style = SUPPLY_GRADE_STYLE[grade] || SUPPLY_GRADE_STYLE.D;
  return (
    <div className="flex items-center gap-2">
      <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-bold ${style.color} ${style.bg}`}>
        {style.label}
      </span>
      {typeof score === "number" && (
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          {score.toFixed(1)}점
        </span>
      )}
    </div>
  );
}

function BoolBadge({ value, trueText, falseText }: { value: boolean; trueText: string; falseText: string }) {
  return value ? (
    <span className="inline-flex items-center gap-1 text-green-700 dark:text-green-400 font-semibold">
      <CheckCircle2 className="w-4 h-4" /> {trueText}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-slate-400 dark:text-slate-500">
      <XCircle className="w-4 h-4" /> {falseText}
    </span>
  );
}

function NetBuyCell({ value }: { value: number }) {
  const b = value / 1e8;
  const isPositive = b > 0;
  const isNegative = b < 0;
  return (
    <span
      className={`font-mono font-semibold ${
        isPositive
          ? "text-red-600 dark:text-red-400"
          : isNegative
          ? "text-blue-600 dark:text-blue-400"
          : "text-slate-500"
      }`}
    >
      {isPositive ? "+" : ""}
      {b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억
    </span>
  );
}

export default async function StockReportPage({
  params,
}: {
  params: { date: string; ticker: string };
}) {
  const resolvedParams = await params;
  const { date, ticker } = resolvedParams;
  const data = await getReportDetail(date, ticker);

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">
            해당 리포트가 없습니다
          </h1>
          <p className="text-slate-500">
            {date} / {ticker} 에 대한 종목 리포트를 찾을 수 없습니다.
          </p>
          <Link
            href="/"
            className="inline-flex items-center text-indigo-600 hover:text-indigo-800"
          >
            <ArrowLeft className="w-4 h-4 mr-1" /> 메인으로 돌아가기
          </Link>
        </div>
      </div>
    );
  }

  const { report: r, content_analyses: contentAnalyses = [] } = data;
  const supplyHistory = r.supply_history ?? [];

  const contentCount = contentAnalyses.length;
  const contentAvgScore =
    contentCount > 0
      ? contentAnalyses.reduce((s, c) => s + (c.sentiment_score ?? 50), 0) / contentCount
      : 0;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
        {/* 네비게이션 */}
        <div className="flex items-center gap-3">
          <Link
            href={`/reports/${date}`}
            className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            {date} 리포트
          </Link>
          <div className="ml-auto">
            <FixedLossCalculator ticker={r.stock_code} />
          </div>
        </div>

        {/* 헤더 */}
        <header>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <h1 className="text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
              {r.stock_name}
            </h1>
            <span className="font-mono text-base font-bold text-slate-400">
              {r.stock_code}
            </span>
            <StockPriceBadge ticker={r.stock_code} date={date} />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-extrabold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              #{r.rank_no}위
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-extrabold tabular-nums text-slate-700 dark:bg-slate-800 dark:text-slate-200">
              {r.score.toFixed(0)}점 / 100
            </span>
          </div>
        </header>

        {/* 다음날 아침 갭 체크 결과 */}
        {(typeof r.gap_nxt_pct === "number" || typeof r.gap_krx_pct === "number") && (() => {
          const hasNxt = typeof r.gap_nxt_pct === "number" && r.gap_nxt_price != null;
          const hasKrx = typeof r.gap_krx_pct === "number" && r.gap_krx_price != null;
          // 텔레그램 포맷과 동일: NXT+KRX 둘 다 있으면 KRX는 NXT→KRX 장중 델타
          const krxIntraday =
            hasNxt && hasKrx && r.gap_nxt_price! > 0
              ? ((r.gap_krx_price! - r.gap_nxt_price!) / r.gap_nxt_price!) * 100
              : null;
          return (
          <Card className="border-0 bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 rounded-3xl shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Sunrise className="w-5 h-5 text-amber-500" />
                다음날 아침 갭 체크
                {r.gap_checked_at && (
                  <span className="ml-auto text-xs font-normal text-slate-500">
                    {new Date(r.gap_checked_at).toLocaleString("ko-KR", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: "Asia/Seoul",
                    })}{" "}
                    기준
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                리포트 시각 가격: <span className="font-bold tabular-nums">{r.current_price.toLocaleString("ko-KR")}</span>원
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {hasNxt && (
                  <GapResultBox
                    label="장 시작 전 (NXT)"
                    sublabel="리포트가 → NXT"
                    pct={r.gap_nxt_pct!}
                    fromPrice={r.current_price}
                    toPrice={r.gap_nxt_price!}
                  />
                )}
                {hasKrx && (
                  <GapResultBox
                    label="장 시작 후 (KRX)"
                    sublabel={krxIntraday !== null ? "NXT → KRX (장중)" : "리포트가 → KRX"}
                    pct={krxIntraday !== null ? krxIntraday : r.gap_krx_pct!}
                    fromPrice={krxIntraday !== null ? r.gap_nxt_price! : r.current_price}
                    toPrice={r.gap_krx_price!}
                  />
                )}
              </div>
              {hasNxt && hasKrx && (
                <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                  리포트가 → KRX 누적{" "}
                  <span
                    className={`font-extrabold tabular-nums ${
                      r.gap_krx_pct! > 0
                        ? "text-rose-600 dark:text-rose-400"
                        : r.gap_krx_pct! < 0
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-slate-500"
                    }`}
                  >
                    {r.gap_krx_pct! > 0 ? "+" : ""}
                    {r.gap_krx_pct!.toFixed(2)}%
                  </span>
                </p>
              )}
            </CardContent>
          </Card>
          );
        })()}

        {/* 1. 종목 기본 정보 카드 */}
        <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Building2 className="w-5 h-5 text-slate-500" />
              종목 기본 정보
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="space-y-1">
                <p className="text-xs text-slate-500 font-medium">섹터</p>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  {r.sector || "기타"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-slate-500 font-medium">시가총액</p>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  {formatMarketCap(r.market_cap)}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-slate-500 font-medium">대장주 여부</p>
                <BoolBadge
                  value={r.is_leader}
                  trueText="섹터 대장"
                  falseText="일반"
                />
              </div>
              <div className="space-y-1">
                <p className="text-xs text-slate-500 font-medium">등락률</p>
                <p
                  className={`text-sm font-bold ${
                    r.change_pct > 0
                      ? "text-red-600 dark:text-red-400"
                      : r.change_pct < 0
                      ? "text-blue-600 dark:text-blue-400"
                      : "text-slate-600"
                  }`}
                >
                  {r.change_pct > 0 ? "+" : ""}
                  {r.change_pct.toFixed(2)}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 2. 거래대금 & 수급등급 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <BarChart3 className="w-5 h-5 text-slate-500" />
                거래대금
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-slate-800 dark:text-slate-100">
                {formatTradingValue(r.trading_value)}
                <span className="text-base font-normal text-slate-500 ml-1">억원</span>
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {r.trading_value >= 200_000_000_000
                  ? "우수 (2,000억 이상)"
                  : r.trading_value >= 100_000_000_000
                  ? "보통 (1,000억 이상)"
                  : "저조"}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Activity className="w-5 h-5 text-slate-500" />
                수급 등급
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SupplyGradeBadge grade={r.supply_grade} score={r.supply_score} />
              <p className="text-xs text-slate-400 mt-2">
                연속 수급 <span className="font-bold text-slate-700 dark:text-slate-300">{r.supply_days}일</span>
              </p>
            </CardContent>
          </Card>
        </div>

        {/* 3. 최근 5일 수급 동향 */}
        <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <TrendingUp className="w-5 h-5 text-slate-500" />
              최근 5일 수급 동향
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="text-left py-3 px-2 text-slate-500 font-medium">
                      날짜
                    </th>
                    <th className="text-right py-3 px-2 text-slate-500 font-medium">
                      개인
                    </th>
                    <th className="text-right py-3 px-2 text-slate-500 font-medium">
                      외국인
                    </th>
                    <th className="text-right py-3 px-2 text-slate-500 font-medium">
                      기관
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {supplyHistory.length > 0 ? (
                    supplyHistory.map((h: SupplyHistoryItem, i: number) => (
                      <tr
                        key={h.date}
                        className={`border-b border-slate-100 dark:border-slate-800 ${
                          i === 0
                            ? "bg-indigo-50/50 dark:bg-indigo-900/10"
                            : ""
                        }`}
                      >
                        <td className="py-3 px-2 font-medium text-slate-700 dark:text-slate-300">
                          {h.date}
                          {i === 0 && (
                            <span className="ml-1 text-xs text-indigo-500">
                              (오늘)
                            </span>
                          )}
                        </td>
                        <td className="text-right py-3 px-2">
                          <NetBuyCell value={h.indv_net_buy} />
                        </td>
                        <td className="text-right py-3 px-2">
                          <NetBuyCell value={h.frgn_net_buy} />
                        </td>
                        <td className="text-right py-3 px-2">
                          <NetBuyCell value={h.inst_net_buy} />
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={4}
                        className="py-8 text-center text-slate-400"
                      >
                        수급 이력 데이터가 없습니다
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* 4. 차트 분석 (캔들차트 + 이평선 정배열) */}
        <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Activity className="w-5 h-5 text-slate-500" />
              차트 분석
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* 캔들차트 */}
            <CandlestickChart data={r.hourly_candles ?? []} />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50 space-y-3">
                <p className="text-sm text-slate-500 font-medium">
                  이동평균 정배열 (5MA &gt; 10MA &gt; 20MA)
                </p>
                <BoolBadge
                  value={r.ma_aligned}
                  trueText="정배열 확인"
                  falseText="정배열 아님"
                />
                <p className="text-xs text-slate-400">
                  5일선이 10일선 위, 10일선이 20일선 위이며 종가가 5일선 위에 있는 상태
                </p>
              </div>
              <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50 space-y-3">
                <p className="text-sm text-slate-500 font-medium">
                  52주 신고가 근접 (95% 이상)
                </p>
                <BoolBadge
                  value={r.near_high}
                  trueText="신고가 근접"
                  falseText="신고가 미달"
                />
                <p className="text-xs text-slate-400">
                  현재가가 52주 최고가의 95% 이상일 때 강한 상승 모멘텀으로 판단
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 5. 콘텐츠 분석 (유튜브/텔레그램) */}
        {contentCount > 0 && (
        <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Newspaper className="w-5 h-5 text-slate-500" />
              콘텐츠 분석
              <span className="ml-auto text-sm font-normal text-slate-500">
                {contentCount}건 / 평균 감성점수{" "}
                <span
                  className={`font-bold ${
                    contentAvgScore >= 60
                      ? "text-red-600 dark:text-red-400"
                      : contentAvgScore >= 40
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-blue-600 dark:text-blue-400"
                  }`}
                >
                  {contentAvgScore.toFixed(0)}
                </span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
                {contentAnalyses.map((c) => (
                  <div
                    key={c.id}
                    className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {c.platform === "youtube" ? (
                          <Youtube className="w-4 h-4 text-red-500 shrink-0" />
                        ) : (
                          <MessageCircle className="w-4 h-4 text-sky-500 shrink-0" />
                        )}
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
                          {c.title}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${
                            c.sentiment_score >= 60
                              ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400"
                              : c.sentiment_score >= 40
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400"
                              : "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"
                          }`}
                        >
                          {c.sentiment_score}점
                        </span>
                        {c.source_url && (
                          <a
                            href={c.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-indigo-500 transition-colors"
                          >
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">
                      {c.source_name}
                      {c.created_at && (
                        <span className="ml-2">
                          {new Date(c.created_at).toLocaleTimeString("ko-KR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
          </CardContent>
        </Card>
        )}

        {/* 6. 점수 상세 (점수 브레이크다운) */}
        <Card className="border-0 bg-white dark:bg-slate-900/60 rounded-3xl shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Crown className="w-5 h-5 text-slate-500" />
              종합 점수 상세
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <ScoreRow
                label="수급 점수"
                value={Math.round((r.supply_score ?? 0) * 0.4)}
                max={40}
              />
              <ScoreRow
                label="이평선 정배열"
                value={r.ma_aligned ? 10 : 0}
                max={10}
              />
              <ScoreRow
                label="52주 신고가 근접"
                value={r.near_high ? 10 : 0}
                max={10}
              />
              <ScoreRow
                label="거래대금"
                value={
                  r.trading_value >= 200_000_000_000
                    ? 15
                    : r.trading_value >= 100_000_000_000
                    ? 8
                    : 0
                }
                max={15}
              />
              <ScoreRow
                label="섹터 대장주"
                value={r.is_leader ? 10 : 0}
                max={10}
              />
              <ScoreRow
                label="오늘의 테마주"
                value={r.is_theme_stock ? 15 : 0}
                max={15}
              />
              <ScoreRow
                label="연속 수급"
                value={Math.min(r.supply_days, 5) * 3}
                max={15}
              />
              <ScoreRow
                label="콘텐츠 분석"
                value={r.content_score}
                max={10}
              />
              <div className="pt-3 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between">
                <span className="font-bold text-slate-800 dark:text-slate-200">
                  총합
                </span>
                <span className="text-xl font-bold text-indigo-600 dark:text-indigo-400">
                  {r.score.toFixed(0)} / 125
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 면책 */}
        <p className="text-xs text-slate-400 text-center pb-8">
          본 리포트는 AI가 자동 생성한 참고 자료이며, 투자 판단의 근거로 사용해서는 안 됩니다.
        </p>
      </div>
    </main>
  );
}

function GapResultBox({
  label,
  sublabel,
  pct,
  fromPrice,
  toPrice,
}: {
  label: string;
  sublabel?: string;
  pct: number;
  fromPrice: number;
  toPrice: number | null;
}) {
  const isUp = pct > 0;
  const isDown = pct < 0;
  return (
    <div className="rounded-2xl bg-white/70 p-4 dark:bg-slate-900/40">
      <p className="text-xs font-bold text-slate-500 dark:text-slate-400">{label}</p>
      {sublabel && (
        <p className="text-[10px] font-medium text-slate-400">{sublabel}</p>
      )}
      <p
        className={`mt-1 text-2xl font-extrabold tabular-nums ${
          isUp
            ? "text-rose-600 dark:text-rose-400"
            : isDown
              ? "text-blue-600 dark:text-blue-400"
              : "text-slate-500"
        }`}
      >
        {isUp ? "+" : ""}
        {pct.toFixed(2)}%
      </p>
      {toPrice != null && (
        <p className="mt-1 text-xs text-slate-500 tabular-nums">
          {fromPrice.toLocaleString("ko-KR")} → {toPrice.toLocaleString("ko-KR")}원
        </p>
      )}
    </div>
  );
}

function ScoreRow({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 text-sm text-slate-600 dark:text-slate-400 shrink-0">
        {label}
      </span>
      <div className="flex-1 h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 dark:bg-indigo-400 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-16 text-right text-sm font-mono font-semibold text-slate-700 dark:text-slate-300">
        {value}/{max}
      </span>
    </div>
  );
}
