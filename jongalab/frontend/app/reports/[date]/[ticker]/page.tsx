import { StockReportDetail, SupplyHistoryItem } from "@/types";
import { StockPriceBadge } from "@/components/StockPriceBadge";
import { CandlestickChart } from "@/components/CandlestickChart";
import { MaterialBadge, materialAxisLabels } from "@/components/MaterialBadge";
import { apiFetch, getEdgeRules } from "@/lib/api";
import { humanizeMaterialReason, splitHeadlineUrl } from "@/lib/news";
import {
  formatBillion,
  formatMarketCap,
  formatWon,
  gapBasePrice,
  morningSentence,
  reportLede,
  reportMetaDescription,
} from "@/lib/report";
import { RichText } from "@/components/ui/rich-text";
import { PANEL, INSET } from "@/lib/ui";
import { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  TrendingUp,
  BarChart3,
  Activity,
  Newspaper,
  ExternalLink,
  Youtube,
  MessageCircle,
  Sunrise,
  FlaskConical,
} from "lucide-react";
import { WhyPicked } from "@/components/pick/WhyPicked";
import { TradePlan } from "@/components/pick/TradePlan";
import { ScoreGauge } from "@/components/pick/ScoreGauge";

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
  ticker: string,
): Promise<StockReportDetail | null> {
  return apiFetch(
    `/api/stock-report/${date}/${ticker}`,
    null,
    fetchOptions(date),
  );
}

/** 선정 근거 룰 → 화면에 낼 한글 제목 + 링크 경로.
 *
 * `rule_names` 는 코드 슬러그(f5_prog_persistent)라 사용자에게 그대로 보여줄 값이 아니다.
 * 실험실 카드와 같은 한글 제목(edge_rule.title)을 쓰고, 슬러그는 링크 경로로만 남긴다
 * (title 이 비어 있으면 실험실 화면과 동일하게 슬러그로 폴백).
 */
async function getRuleChips(
  ruleNames: string[],
): Promise<{ name: string; label: string }[]> {
  if (ruleNames.length === 0) return [];
  const rules = await getEdgeRules();
  const titleByName = new Map(rules.map((x) => [x.name, x.title]));
  return ruleNames.map((name) => ({
    name,
    label: titleByName.get(name) || name,
  }));
}

export async function generateMetadata({
  params,
}: {
  params: { date: string; ticker: string };
}): Promise<Metadata> {
  const resolvedParams = await params;
  const data = await getReportDetail(
    resolvedParams.date,
    resolvedParams.ticker,
  );

  if (!data) {
    return { title: "리포트를 찾을 수 없어요" };
  }

  const r = data.report;
  // 제목은 `{종목명} 투자분석 - {YYYY.MM.DD}` — 앞머리에 **실제로 검색되는 키워드**를 두고
  // 날짜는 뒤로 뺀다. 날짜를 앞세우면 "종목명 날짜 종가" 같은 시세 조회 쿼리에만 걸린다.
  // description 은 본문 리드와 같은 빌더(`lib/report`)를 쓴다 — 스니펫과 본문이 갈리지 않게.
  // 근거: docs/plan/seo/search-visibility.md
  const title = `${r.stock_name} 투자분석 - ${resolvedParams.date.replace(/-/g, ".")}`;
  const description = reportMetaDescription(r, resolvedParams.date);

  return {
    title,
    description,
    alternates: {
      canonical: `/reports/${resolvedParams.date}/${resolvedParams.ticker}`,
    },
    openGraph: {
      title,
      description,
      url: `https://jongalab.com/reports/${resolvedParams.date}/${resolvedParams.ticker}`,
      siteName: "종가랩",
      type: "article",
    },
  };
}

/** 수급 등급 칩 색 — 등급 뜻(관심권·수급 약함…)은 '왜 뽑혔나' 축이 내므로 여기선 색만 갖는다. */
const SUPPLY_GRADE_CHIP: Record<string, string> = {
  S: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  A: "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300",
  B: "bg-yellow-100 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300",
  C: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  D: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

/** 조건 충족 여부 칩 — 참이면 색면, 아니면 회색으로 눕힌다(색 단독 표시가 아니라 문구가 라벨). */
function ConditionChip({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold ${
        on
          ? "bg-teal-100 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300"
          : "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
      }`}
    >
      {on ? "○" : "×"} {label}
    </span>
  );
}

function NetBuyCell({ value }: { value: number | null | undefined }) {
  const b = (value ?? 0) / 1e8;
  return (
    <td
      className={`py-2 px-1.5 text-right font-mono text-[11px] font-semibold tabular-nums sm:text-xs ${
        b > 0
          ? "text-red-600 dark:text-red-400"
          : b < 0
            ? "text-blue-600 dark:text-blue-400"
            : "text-slate-400"
      }`}
    >
      {b > 0 ? "+" : ""}
      {b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}
    </td>
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
            이 리포트가 없어요
          </h1>
          <p className="text-slate-500">
            {date} / {ticker} 종목 리포트를 찾을 수 없어요.
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

  const {
    report: r,
    content_analyses: contentAnalyses = [],
    score_breakdown: breakdown = null,
  } = data;
  const ruleChips = await getRuleChips(
    (r.rule_names ?? "").split(",").filter(Boolean),
  );
  const lede = reportLede(
    r,
    date,
    ruleChips.map((c) => c.label),
  );
  const hasNews = (r.news_count ?? 0) > 0;
  const hasContent = contentAnalyses.length > 0;

  return (
    <main className="min-h-screen">
      {/* 세로 리듬은 섹션 간 gap 하나로 통일한다 — 카드 안쪽 여백은 `PANEL` 이 갖는다. */}
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6 sm:py-8">
        <Link
          href={`/reports/${date}`}
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          {date} 추천 목록
        </Link>

        {/* 헤더 — 종목·시세·선정 배지 + 기본 정보 한 줄 + 리드 문단.
            ⚠️ **값 하나짜리 카드를 만들지 않는다** — 섹터·가격·거래대금 같은 단일 값은 이 `dl` 한 줄에
            모으고, 리드 문단이 같은 사실을 문장으로 한 번 더 낸다(검색 유입용 본문).
            경위: docs/history/frontend-ui.md */}
        <header>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
              {r.stock_name}
            </h1>
            <span className="font-mono text-base font-bold text-slate-400">
              {r.stock_code}
            </span>
            <StockPriceBadge ticker={r.stock_code} date={date} />
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-extrabold tabular-nums text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              종합 {r.score.toFixed(0)}점 · 점수 {r.rank_no}위
            </span>
            {/* 룰 선정 종목(hybrid) — 점수 순위와 무관하게 실험실 룰이 뽑았다. 근거 룰로 넘어간다. */}
            {ruleChips.map((c) => (
              <Link
                key={c.name}
                href={`/lab/${encodeURIComponent(c.name)}`}
                title="실험실에서 성적을 확인한 전략이 이 종목을 골랐어요 (점수 순위와는 관계없어요) — 눌러서 전략 성적 보기"
                className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-1 text-xs font-extrabold text-violet-700 hover:bg-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:hover:bg-violet-900/60"
              >
                <FlaskConical className="h-3.5 w-3.5 shrink-0" />
                <span className="break-keep">{c.label}</span>
                <span className="font-bold text-violet-500 dark:text-violet-400">
                  선정
                </span>
              </Link>
            ))}
          </div>

          <dl className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1.5 text-xs">
            {[
              { label: "섹터", value: r.sector || "기타" },
              { label: "리포트가", value: `${formatWon(r.current_price)}원` },
              {
                label: "당일 등락",
                value: `${r.change_pct > 0 ? "+" : ""}${r.change_pct.toFixed(2)}%`,
                tone:
                  r.change_pct > 0
                    ? "text-red-600 dark:text-red-400"
                    : r.change_pct < 0
                      ? "text-blue-600 dark:text-blue-400"
                      : undefined,
              },
              {
                label: "거래대금",
                value: `${formatBillion(r.trading_value)}원`,
              },
              { label: "시가총액", value: formatMarketCap(r.market_cap) },
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
        </header>

        {/* 요약 밴드 — 도입 문단 + 근거 3축. 화면 폭 전체를 쓰고 3축이 데스크탑에서 가로로 눕는다.
            2단 영역 위에 두는 이유: '왜 뽑혔나' 는 이 화면의 본론이라 모바일·데스크탑 모두 먼저 읽혀야 한다. */}
        <WhyPicked report={r} lede={lede} />

        {/* 카드 배치 — 데스크탑은 **짝이 고정된 2열 밴드 3줄**이다.
            ⚠️ 2열 다단(`columns-2`)으로 되돌리지 말 것 — 열 나눔을 브라우저에 맡기면 카드 수가
            날마다 달라 열끝 차가 0~444px 로 튄다(10가지 데이터 조합 실측). 짝을 고정하고 각 짝의
            높이를 **설계로** 맞추면(점수↔매매·결과 / 수급↔차트) 어느 날이든 차가 예측 가능하다.
            재료 줄은 둘 중 하나만 있는 날 **전체 폭**으로 낸다 — 빈 절반이 '카드가 빠진 자리'로 보인다.
            모바일(<lg)은 1열이라 DOM 순서가 곧 화면 순서다: 점수 → 매매·결과 → 수급 → 차트 → 재료. */}
        {/* 이 짝만 `lg:` 부터 2열이다 — 768px 에서는 열이 352px 라 매매 카드의 3칸이 세로로 쌓여
            높이가 두 배(334 vs 614)가 되고, 그 차이가 점수 카드 안 빈 공간으로 남는다. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ScoreGauge report={r} breakdown={breakdown} />
          {/* 매매 전제 + 그 결과는 한 카드다(결과가 없는 날 토막 카드가 남지 않게) */}
          <TradePlan report={r} footer={<MorningResultBlock report={r} />} />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SupplySection report={r} />
          <ChartSection report={r} />
        </div>

        {(hasNews || hasContent) && (
          <div
            className={
              hasNews && hasContent
                ? "grid grid-cols-1 gap-4 md:grid-cols-2 md:items-start"
                : undefined
            }
          >
            {hasNews && <NewsSection report={r} />}
            {hasContent && <ContentSection items={contentAnalyses} />}
          </div>
        )}

        <p className="pb-6 text-center text-xs break-keep text-slate-400">
          이 리포트는 AI가 자동으로 만든 참고 자료예요. 이것만 보고 투자를
          결정하면 안 돼요.
        </p>
      </div>
    </main>
  );
}

/** 다음 거래일 아침 결과 — 갭(참조가 기준)·실체결(체결가 기준) + 한 문장 설명.
 *
 * 독립 카드가 아니라 **'어떻게 매매하나' 카드 안 블록**이다: 전제와 그 결과는 한 장에서 읽는 게 맞고,
 * 결과가 없는 날에 따로 카드를 두면 100px 짜리 토막 카드가 남는다(측정으로 확인).
 */
function MorningResultBlock({
  report: r,
}: {
  report: StockReportDetail["report"];
}) {
  const hasNxt = typeof r.gap_nxt_pct === "number" && r.gap_nxt_price != null;
  const hasKrx = typeof r.gap_krx_pct === "number" && r.gap_krx_price != null;
  // 텔레그램 포맷과 동일: NXT+KRX 둘 다 있으면 KRX는 NXT→KRX 장중 델타
  const krxIntraday =
    hasNxt && hasKrx && r.gap_nxt_price! > 0
      ? ((r.gap_krx_price! - r.gap_nxt_price!) / r.gap_nxt_price!) * 100
      : null;
  const exRatio = r.gap_ex_rights_ratio ?? null;
  const basePrice = gapBasePrice(r);

  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h3 className="flex items-center gap-1.5 text-sm font-extrabold text-slate-700 dark:text-slate-200">
          <Sunrise className="h-4 w-4 text-amber-500" />
          다음 거래일 아침 결과
        </h3>
        {r.gap_checked_at && (
          <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
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
      </div>

      {exRatio && (
        <p className="mt-2 rounded-2xl bg-amber-50 px-3 py-2 text-[11px] leading-relaxed break-keep text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <span className="font-bold">무상증자 권리락일</span> — 1주당 신주{" "}
          {exRatio}주 배정으로 기준가가{" "}
          <span className="font-bold tabular-nums">{formatWon(basePrice)}</span>
          원으로 낮아졌어요. 아래 등락률은 낮아진 기준 가격과 비교한 실제
          움직임이에요.
        </p>
      )}

      {(hasNxt || hasKrx) && (
        <>
          <div className="mt-2 space-y-2">
            {hasNxt && (
              <GapResultBox
                label="장 시작 전 (NXT)"
                sublabel={exRatio ? "권리락 기준가 → NXT" : "리포트가 → NXT"}
                pct={r.gap_nxt_pct!}
                fromPrice={basePrice}
                toPrice={r.gap_nxt_price!}
              />
            )}
            {hasKrx && (
              <GapResultBox
                label="정규장 (KRX)"
                sublabel={
                  krxIntraday !== null
                    ? "NXT → KRX (장중)"
                    : exRatio
                      ? "권리락 기준가 → KRX"
                      : "리포트가 → KRX"
                }
                pct={krxIntraday !== null ? krxIntraday : r.gap_krx_pct!}
                fromPrice={krxIntraday !== null ? r.gap_nxt_price! : basePrice}
                toPrice={r.gap_krx_price!}
              />
            )}
          </div>

          {/* 누적(참조가 기준)과 실체결(체결가 기준)은 어긋날 수 있어 어느 쪽이 실제인지 밝혀 둔다. */}
          {(hasNxt && hasKrx) || typeof r.exec_leg_ret === "number" ? (
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
              {hasNxt && hasKrx && (
                <span>
                  리포트가 → KRX 누적 <PctText pct={r.gap_krx_pct!} />
                </span>
              )}
              {typeof r.exec_leg_ret === "number" && (
                <span>
                  실제 체결 <PctText pct={r.exec_leg_ret} />
                  {r.exec_leg_venue && (
                    <span className="ml-0.5 text-slate-400">
                      ({r.exec_leg_venue})
                    </span>
                  )}
                </span>
              )}
            </p>
          ) : null}
        </>
      )}

      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-500 dark:text-slate-400">
        <RichText parts={morningSentence(r)} />
      </p>
    </>
  );
}

function PctText({ pct }: { pct: number }) {
  return (
    <span
      className={`font-extrabold tabular-nums ${
        pct > 0
          ? "text-rose-600 dark:text-rose-400"
          : pct < 0
            ? "text-blue-600 dark:text-blue-400"
            : "text-slate-500"
      }`}
    >
      {pct > 0 ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
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
  return (
    <div className={`${INSET} px-3 py-2`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-bold text-slate-500 dark:text-slate-400">
          {label}
        </p>
        <p className="text-xl font-extrabold">
          <PctText pct={pct} />
        </p>
      </div>
      <div className="mt-0.5 flex items-baseline justify-between gap-2 text-[10px] font-medium text-slate-400 dark:text-slate-500">
        <span>{sublabel}</span>
        {toPrice != null && (
          <span className="tabular-nums">
            {formatWon(fromPrice)} → {formatWon(toPrice)}원
          </span>
        )}
      </div>
    </div>
  );
}

/** 수급 — 등급·연속일을 헤더에 두고 본문은 5일 표 하나. 등급 카드를 따로 두지 않는다(값 하나짜리 카드). */
function SupplySection({ report: r }: { report: StockReportDetail["report"] }) {
  const supplyHistory = r.supply_history ?? [];
  const gradeChip = SUPPLY_GRADE_CHIP[r.supply_grade] ?? SUPPLY_GRADE_CHIP.D;

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <TrendingUp className="h-4.5 w-4.5 text-purple-800 dark:text-purple-300" />
          수급
        </h2>
        <div className="flex items-center gap-1.5">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-extrabold ${gradeChip}`}
          >
            {r.supply_grade}등급 {r.supply_score.toFixed(0)}점
          </span>
          <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
            연속 {r.supply_days}일
          </span>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] text-slate-400 dark:border-slate-700 dark:text-slate-500">
              <th className="py-1.5 px-1.5 text-left font-medium">날짜</th>
              <th className="py-1.5 px-1.5 text-right font-medium">개인</th>
              <th className="py-1.5 px-1.5 text-right font-medium">외국인</th>
              <th className="py-1.5 px-1.5 text-right font-medium">기관</th>
              <th className="py-1.5 px-1.5 text-right font-medium">프로그램</th>
            </tr>
          </thead>
          <tbody>
            {supplyHistory.length > 0 ? (
              supplyHistory.map((h: SupplyHistoryItem, i: number) => (
                <tr
                  key={h.date}
                  className={`border-b border-slate-100 dark:border-slate-800 ${
                    i === 0 ? "bg-indigo-50/60 dark:bg-indigo-950/20" : ""
                  }`}
                >
                  <td className="py-2 px-1.5 font-semibold tabular-nums text-slate-600 dark:text-slate-300">
                    {h.date.slice(5).replace("-", ".")}
                    {i === 0 && (
                      <span className="ml-1 text-[10px] font-bold text-indigo-500">
                        기준일
                      </span>
                    )}
                  </td>
                  <NetBuyCell value={h.indv_net_buy} />
                  <NetBuyCell value={h.frgn_net_buy} />
                  <NetBuyCell value={h.inst_net_buy} />
                  <NetBuyCell value={h.prog_net_buy} />
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="py-6 text-center text-slate-400">
                  수급 기록이 없어요
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {/* 5일 합계 — 표의 다섯 줄을 눈으로 더해야 알 수 있던 값이다. 막대는 방향 색(매수 빨강 /
          매도 파랑)이고 길이는 네 주체 중 가장 큰 절대값 기준이다(숫자를 항상 함께 낸다). */}
      {supplyHistory.length > 0 && (
        <div className={`${INSET} mt-3 px-3 py-2.5`}>
          <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400">
            최근 {supplyHistory.length}일 합계
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {supplyTotals(supplyHistory).map(({ label, value, ratio }) => (
              <li key={label} className="flex items-center gap-2">
                <span className="w-12 shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-700/70">
                  <span
                    className={`block h-full rounded-full ${
                      value > 0
                        ? "bg-red-500/80"
                        : value < 0
                          ? "bg-blue-500/80"
                          : "bg-slate-400/60"
                    }`}
                    style={{ width: `${ratio}%` }}
                  />
                </span>
                <span
                  className={`w-16 shrink-0 text-right text-[11px] font-bold tabular-nums ${
                    value > 0
                      ? "text-red-600 dark:text-red-400"
                      : value < 0
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-slate-400"
                  }`}
                >
                  {formatBillion(value, true)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        표의 단위는 억원이고, 그날 사들인 금액이 팔아치운 금액보다 많으면{" "}
        <span className="font-bold text-red-500">빨강(+)</span>, 반대면{" "}
        <span className="font-bold text-blue-500">파랑(−)</span>이에요.
      </p>
    </section>
  );
}

/** 5일 수급 합계 — 표에 있는 값만 더한다(판정·추정은 하지 않는다). 막대 길이는 최대 절대값 기준. */
function supplyTotals(history: SupplyHistoryItem[]) {
  const sum = (pick: (h: SupplyHistoryItem) => number | null | undefined) =>
    history.reduce((acc, h) => acc + (pick(h) ?? 0), 0);
  const rows = [
    { label: "기관", value: sum((h) => h.inst_net_buy) },
    { label: "외국인", value: sum((h) => h.frgn_net_buy) },
    { label: "개인", value: sum((h) => h.indv_net_buy) },
    { label: "프로그램", value: sum((h) => h.prog_net_buy) },
  ];
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return rows.map((r) => ({
    ...r,
    ratio: Math.round((Math.abs(r.value) / maxAbs) * 100),
  }));
}

/** 차트 — 캔들 하나 + 조건 칩 2개. 조건 설명은 박스 두 개가 아니라 아래 한 문장이 담는다. */
function ChartSection({ report: r }: { report: StockReportDetail["report"] }) {
  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <Activity className="h-4.5 w-4.5 text-teal-600 dark:text-teal-300" />
          차트
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <ConditionChip on={r.ma_aligned} label="이동평균 정배열" />
          <ConditionChip on={r.near_high} label="52주 신고가 근접" />
        </div>
      </div>

      <div className="mt-3">
        {/* 상세 본문의 일부라 시장 차트보다 낮게 쓴다(모바일 스크롤). */}
        <CandlestickChart data={r.hourly_candles ?? []} height={280} />
      </div>

      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        최근 1주일 1시간봉이에요. <span className="font-bold">정배열</span>은
        5·10·20일 평균 가격이 차례로 위에 놓이고 현재가가 5일 평균 위에 있는
        상태, <span className="font-bold">신고가 근접</span>은 현재가가 1년
        최고가의 95% 이상이라는 뜻이에요.
      </p>
    </section>
  );
}

/** 뉴스 재료 — 지속성 판정 근거를 반드시 노출한다(등급만 내면 화면에서 오탐 감사가 안 된다). */
function NewsSection({ report: r }: { report: StockReportDetail["report"] }) {
  const headlines = r.news_headlines ?? [];
  const shown = headlines.slice(0, 4);
  const rest = headlines.slice(4);

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <Newspaper className="h-4.5 w-4.5 text-amber-500 dark:text-amber-300" />
          뉴스 재료
        </h2>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          이 날{" "}
          <span className="font-bold text-slate-600 dark:text-slate-300">
            {r.news_count}
          </span>
          건 언급
          {(r.news_unique_count ?? 0) > 0 &&
            r.news_unique_count !== r.news_count && (
              <> · 고유 {r.news_unique_count}건</>
            )}
        </span>
      </div>

      <div className="mt-3 space-y-2.5">
        {(r.news_durability || r.news_label_reason) && (
          <div className={`${INSET} px-3 py-2.5`}>
            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
              <MaterialBadge durability={r.news_durability} showUnjudged />
              {materialAxisLabels(r).map((t) => (
                <span
                  key={t}
                  className="text-[11px] font-medium text-slate-500 dark:text-slate-400"
                >
                  · {t}
                </span>
              ))}
              <span className="ml-auto text-[10px] font-bold text-slate-400 dark:text-slate-500">
                관찰 중 · 미검증
              </span>
            </div>
            {r.news_label_reason && (
              <p className="mt-1.5 break-keep text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                {/* 내부 필드명이 섞인 과거 판정문을 사람 말로 바꿔서 낸다(lib/news) */}
                {humanizeMaterialReason(r.news_label_reason)}
              </p>
            )}
            {r.news_followup_days != null && (
              <p className="mt-1 text-[11px] font-medium text-slate-400 dark:text-slate-500">
                이 재료가 다시 기사에 등장한 날{" "}
                <span className="tabular-nums">{r.news_followup_days}</span>일
                <span className="text-slate-300 dark:text-slate-600">
                  {" "}
                  / 이후 10일 (주가 등락 기사 제외)
                </span>
              </p>
            )}
          </div>
        )}

        {(r.news_catalyst ||
          r.news_sentiment != null ||
          r.news_first_today) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {r.news_catalyst && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {r.news_catalyst}
              </span>
            )}
            {r.news_sentiment != null && (
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  r.news_sentiment > 50
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400"
                    : r.news_sentiment < 50
                      ? "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400"
                      : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                }`}
              >
                {r.news_sentiment > 50
                  ? "호재"
                  : r.news_sentiment < 50
                    ? "악재"
                    : "중립"}{" "}
                {r.news_sentiment}
              </span>
            )}
            {r.news_first_today && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
                첫 등장
              </span>
            )}
          </div>
        )}

        {r.news_summary && (
          <p className="text-xs leading-relaxed break-keep whitespace-pre-line text-slate-700 dark:text-slate-300">
            {r.news_summary}
          </p>
        )}

        {headlines.length > 0 && (
          <div>
            <HeadlineList items={shown} />
            {rest.length > 0 && (
              // 헤드라인이 많은 날 카드가 통째로 길어져 나머지는 접는다(닫혀 있어도 색인은 된다).
              <details className="mt-1.5 group">
                <summary className="cursor-pointer list-none text-[11px] font-bold text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                  헤드라인 {rest.length}건 더 보기
                </summary>
                <div className="mt-1.5">
                  <HeadlineList items={rest} />
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function HeadlineList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((h, i) => {
        const { text, url } = splitHeadlineUrl(h);
        return (
          <li
            key={`${i}-${text.slice(0, 12)}`}
            className="flex gap-1.5 text-xs leading-relaxed break-keep text-slate-600 dark:text-slate-400"
          >
            <span className="shrink-0 text-amber-500">•</span>
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 break-words hover:text-slate-900 hover:underline dark:hover:text-slate-100"
              >
                {text}
              </a>
            ) : (
              <span className="min-w-0 break-words">{text}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** 유튜브·텔레그램 언급 — 4건까지 펼쳐 두고 나머지는 접는다. */
function ContentSection({
  items,
}: {
  items: NonNullable<StockReportDetail["content_analyses"]>;
}) {
  const avg =
    items.reduce((s, c) => s + (c.sentiment_score ?? 50), 0) / items.length;
  const shown = items.slice(0, 4);
  const rest = items.slice(4);

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <BarChart3 className="h-4.5 w-4.5 text-amber-500 dark:text-amber-300" />
          유튜브·텔레그램 언급
        </h2>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          {items.length}건 · 평균 분위기{" "}
          <span className="font-bold text-slate-600 dark:text-slate-300 tabular-nums">
            {avg.toFixed(0)}점
          </span>
        </span>
      </div>

      <ul className="mt-3 space-y-1.5">
        {shown.map((c) => (
          <ContentRow key={c.id} item={c} />
        ))}
      </ul>
      {rest.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer list-none text-[11px] font-bold text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            {rest.length}건 더 보기
          </summary>
          <ul className="mt-1.5 space-y-1.5">
            {rest.map((c) => (
              <ContentRow key={c.id} item={c} />
            ))}
          </ul>
        </details>
      )}
      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        분위기 점수는 AI가 콘텐츠 내용을 읽고 0~100으로 매긴 값이에요(50이
        중립).
      </p>
    </section>
  );
}

function ContentRow({
  item: c,
}: {
  item: NonNullable<StockReportDetail["content_analyses"]>[number];
}) {
  return (
    <li className={`${INSET} flex items-center gap-2 px-3 py-2`}>
      {c.platform === "youtube" ? (
        <Youtube className="h-3.5 w-3.5 shrink-0 text-red-500" />
      ) : (
        <MessageCircle className="h-3.5 w-3.5 shrink-0 text-sky-500" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-bold text-slate-700 dark:text-slate-200">
          {c.title}
        </p>
        <p className="truncate text-[10px] font-medium text-slate-400 dark:text-slate-500">
          {c.source_name}
          {c.created_at && (
            <>
              {" · "}
              {new Date(c.created_at).toLocaleTimeString("ko-KR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </>
          )}
        </p>
      </div>
      <span className="shrink-0 text-[11px] font-extrabold tabular-nums text-slate-500 dark:text-slate-400">
        {c.sentiment_score}
      </span>
      {c.source_url && (
        <a
          href={c.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}
    </li>
  );
}
