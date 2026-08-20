import type { Metadata } from "next";
import Link from "next/link";
import {
  ChevronLeft,
  ChevronRight,
  MessagesSquare,
  Newspaper,
} from "lucide-react";
import {
  ContentAnalysis,
  MentionStats,
  NewsHeatItem,
  NewsMaterialRow,
  NewsStreamItem,
  NewsStreamResponse,
  PaginatedResponse,
} from "@/types";
import { NewsDateNav, formatKoDate } from "@/components/news/NewsDateNav";
import { NewsSummaryStrip } from "@/components/news/NewsSummaryStrip";
import { MaterialBoard } from "@/components/news/MaterialBoard";
import { NewsBuzzRail } from "@/components/news/NewsBuzzRail";
import { NewsStream } from "@/components/news/NewsStream";
import { MentionPulse } from "@/components/news/MentionPulse";
import { ContentCard } from "@/components/ContentCard";
import { ViewSegment } from "@/components/ViewSegment";
import { apiFetch } from "@/lib/api";

export const metadata: Metadata = {
  title: "뉴스 - 오늘의 종목 재료",
  description:
    "그날 종목이 왜 움직였는지, 뉴스에서 찾은 이유(재료)와 기사 제목을 모아 봐요. 유튜브·텔레그램에서 무슨 얘기가 나왔는지도 정리해 줘요.",
  // ?view=·?date=·?page=·?ns= 변형은 기본 경로로 통합해 중복 색인을 방지한다.
  alternates: { canonical: "/news" },
};

export const dynamic = "force-dynamic";

type View = "news" | "content";

const STREAM_PAGE = 40;
const BUZZ_LIMIT = 15;
/** 사이드 랭킹 노이즈 하한 — 2건짜리 종목이 목록을 채우면 '뉴스가 몰린' 랭킹이 아니다. */
const BUZZ_MIN_COUNT = 3;
/** 평소 수준(1.5배 미만)인 종목은 뺀다 — 안 빼면 건수 정렬이 시총 랭킹이 된다. */
const BUZZ_MIN_SURPRISE = 1.5;
const CONTENT_PAGE = 12;

async function getMaterials(date: string): Promise<NewsMaterialRow[]> {
  const res = await apiFetch<{ success: boolean; data: NewsMaterialRow[] } | null>(
    `/api/news/materials?date=${date}`,
    null,
  );
  return res?.data ?? [];
}

/**
 * 사이드 랭킹 데이터 — **배수로 걸러 건수로 정렬**한다.
 * 배수 정렬만 쓰면 분모 하한 탓에 직전 7일 0건인 2~3건 종목이 상단을 채우고 그 날 기사가
 * 가장 많은 종목이 아래로 밀린다(실측·근거: docs/history/frontend-ui.md 2026-08-20).
 */
async function getHeat(date: string): Promise<NewsHeatItem[]> {
  const res = await apiFetch<{ success: boolean; data: NewsHeatItem[] } | null>(
    `/api/news/heat?date=${date}&limit=${BUZZ_LIMIT}` +
      `&min_count=${BUZZ_MIN_COUNT}&min_surprise=${BUZZ_MIN_SURPRISE}&sort=count`,
    null,
  );
  return res?.data ?? [];
}

/** 헤드라인 첫 페이지 — 시세 기사 제외는 **서버가** 한다(총계와 표시 건수를 맞추려고). */
async function getStream(
  date: string,
  ticker?: string,
  limit: number = STREAM_PAGE,
): Promise<{
  items: NewsStreamItem[];
  total: number;
  priceTotal: number;
  hasMore: boolean;
}> {
  const res = await apiFetch<NewsStreamResponse | null>(
    `/api/news/stream?date=${date}&limit=${limit}&hide_price=1` +
      (ticker ? `&ticker=${ticker}` : ""),
    null,
  );
  return {
    items: res?.data ?? [],
    total: res?.total ?? 0,
    priceTotal: res?.price_total ?? 0,
    hasMore: Boolean(res?.has_more),
  };
}

async function getContents(
  page: number,
): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch(`/api/contents?page=${page}&limit=${CONTENT_PAGE}`, {
    success: false,
    data: [],
    pagination: null,
  });
}

async function getMentionStats(): Promise<MentionStats | null> {
  const res = await apiFetch<{ success: boolean; data: MentionStats } | null>(
    `/api/contents/mention-stats`,
    null,
  );
  return res?.success ? res.data : null;
}

/** 날짜 이동은 리포트가 있는 영업일 위를 걷는다 (주말·휴장일을 밟지 않게). */
async function getReportDates(): Promise<string[]> {
  return apiFetch<string[]>(`/api/stock-report/dates?limit=60`, []);
}

function todayStr(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TICKER_RE = /^[0-9A-Za-z]{4,12}$/;

/**
 * 뉴스 탭 — **뉴스**(기사 기반 재료)와 **콘텐츠**(유튜브·텔레그램 분석)를 세그먼트로 나눈다.
 * 둘 다 '어떤 재료가 돌고 있나'라는 같은 질문이지만 출처·시간축이 달라 한 화면에 쌓으면
 * 스크롤만 길어졌다. 시장 탭과 같은 방식이라 목적지(탭)는 늘지 않고 canonical 도 `/news` 하나다.
 *
 * 뉴스 뷰는 그 날의 뉴스판을 **요약 → 종목별 재료 → 원문 헤드라인** 순으로 보여준다.
 *
 * 구성 세 층: **요약 카드**(`NewsSummaryStrip`) → **종목별 재료 단일 목록 + 필터/정렬**
 * (`MaterialBoard`) → **원문 헤드라인 스트림**(`NewsStream`). 날짜 이동은 `NewsDateNav`.
 *   · 모바일 순서는 재료 목록 → 사이드 랭킹 → 헤드라인이다. 랭킹을 스트림 뒤에 두면
 *     40건 목록을 지나야 나와서 사실상 도달하지 못한다(그래서 그리드 배치를 명시한다).
 *   · 재료를 등급 그룹으로 미리 가르지 않는다 — 절반 이상이 '판정 보류'로 떨어져 가장 큰 그룹이
 *     "판정 못 함"이 된다. 등급은 필터 칩으로만 쓴다.
 *   · 후보 밖 종목은 `NewsBuzzRail`(뉴스량 랭킹)이 덮는다. 재료 목록은 후보 종목만 다뤄서
 *     그것만으로는 그 날 뉴스판의 일부만 보인다.
 *   · 헤드라인 소스는 **네이버 증권 섹션**(`sec_news`)이다. 종합 속보 채널을 모집단으로 쓰면
 *     주식과 무관한 기사가 섞인다(sql/49 — 라벨·rule 표본은 그대로 `news_mention`).
 *
 * ⚠️ 지속성 라벨은 **candidate rule 표본(관찰 전용·미검증)**이다. 면책 문구는 등급 칩이 보이는
 * 자리(`MaterialBoard` 목록 위)의 접이식 안내로 두되, 문구 자체는 줄이지 않는다.
 *
 * 재설계 경위·실측 수치: docs/history/frontend-ui.md · docs/history/news-pipeline.md
 *
 * 모바일 우선: 전부 1열로 흐르고, lg 부터 [본문 | 사이드 레일] 2열.
 */
export default async function NewsPage({
  searchParams,
}: {
  searchParams: Promise<{
    view?: string;
    date?: string;
    page?: string;
    ns?: string;
  }>;
}) {
  const sp = await searchParams;
  const view: View = sp.view === "content" ? "content" : "news";

  return (
    <main className="mx-auto max-w-7xl px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:pb-10">
      {/* 첫 화면(375×667)에서 크롬이 콘텐츠를 밀어내지 않게 헤더를 눌러 둔다 — 눈썹 줄
          ('오늘의 재료')은 h1·부제와 겹쳐 지웠고, 세그먼트는 sm 부터 h1 과 같은 줄에 앉는다. */}
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            뉴스
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            기사에서 찾은 종목이 오를 이유(재료)와, 유튜브·텔레그램 이야기를 나눠서 보여줘요.
          </p>
        </div>
        <ViewSegment
          active={view}
          options={[
            { key: "news", label: "뉴스", icon: Newspaper, href: "/news" },
            {
              key: "content",
              label: "콘텐츠",
              icon: MessagesSquare,
              href: "/news?view=content",
            },
          ]}
        />
      </header>

      <div className="mt-5">
        {view === "news" ? (
          <NewsView date={sp.date} streamTicker={sp.ns} />
        ) : (
          <ContentView page={Number(sp.page) || 1} />
        )}
      </div>
    </main>
  );
}

async function NewsView({
  date: requestedDate,
  streamTicker,
}: {
  date?: string;
  /** 재료 목록에서 '이 종목 기사만' 으로 넘어온 종목코드 (`?ns=`) */
  streamTicker?: string;
}) {
  const dates = await getReportDates();
  const requested =
    requestedDate && DATE_RE.test(requestedDate) ? requestedDate : null;
  // 기본은 '가장 최근 리포트일'이다. 오늘로 고정하면 휴장일·장 시작 전에 통째로 빈 화면이 된다.
  const date = requested ?? dates[0] ?? todayStr();
  const ticker = streamTicker && TICKER_RE.test(streamTicker) ? streamTicker : undefined;

  const [rows, heat, stream, dayCount] = await Promise.all([
    getMaterials(date),
    getHeat(date),
    getStream(date, ticker),
    // 요약 카드의 기사 수는 **그 날 전체**여야 한다 — `?ns=` 필터는 스트림에만 걸리는데
    // 같은 응답을 요약에 재사용하면 "모아 온 기사 9건" 처럼 하루 규모가 종목 규모로 줄어든다.
    ticker ? getStream(date, undefined, 1) : null,
  ]);
  const dayStream = dayCount ?? stream;

  const isToday = date === todayStr();
  const tickerLabel = rows.find((r) => r.stock_code === ticker)?.stock_name;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold text-slate-400 dark:text-slate-500">
          {isToday ? "오늘" : formatKoDate(date)} 기준
        </p>
        <NewsDateNav date={date} dates={dates} />
      </div>

      <div className="mt-3 mb-6">
        <NewsSummaryStrip
          rows={rows}
          articleCount={dayStream.total}
          priceCount={dayStream.priceTotal}
        />
      </div>

      {/* 자리를 명시한다 — 자동 배치에 맡기면 사이드 레일의 grid area 가 1행으로 잘려
          sticky 가 재료 목록 높이에서 멈춘다. 모바일은 1열이라 DOM 순서대로 흐른다. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-8">
        <div className="min-w-0 lg:col-start-1 lg:row-start-1">
          {rows.length === 0 ? (
            <p className="rounded-2xl bg-white p-6 text-center text-sm font-medium text-slate-400 dark:bg-slate-900/60">
              이 날은 뉴스가 붙은 후보 종목이 없어요.
            </p>
          ) : (
            <MaterialBoard rows={rows} date={date} />
          )}
        </div>

        <aside className="min-w-0 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:sticky lg:top-20 lg:self-start">
          <NewsBuzzRail items={heat} date={date} />
        </aside>

        <div className="min-w-0 lg:col-start-1 lg:row-start-2">
          <NewsStream
            date={date}
            initial={stream.items}
            total={stream.total}
            priceTotal={stream.priceTotal}
            hasMore={stream.hasMore}
            ticker={ticker}
            tickerLabel={tickerLabel}
            clearTickerHref={`/news?date=${date}#headlines`}
          />
        </div>
      </div>
    </>
  );
}

/** 콘텐츠 뷰 — 언급 트리맵 + 페이지네이션 목록(`/feed` 탭을 흡수한 본문). */
async function ContentView({ page }: { page: number }) {
  const [contentsRes, mentionStats] = await Promise.all([
    getContents(page),
    getMentionStats(),
  ]);
  const data = contentsRes.data || [];
  const pagination = contentsRes.pagination;

  return (
    <div className="space-y-6">
      <MentionPulse stats={mentionStats} />

      <section>
        <div className="mb-3 flex items-end justify-between gap-2">
          <h2 className="text-lg font-extrabold tracking-tight text-slate-900 sm:text-xl dark:text-slate-100">
            콘텐츠 분석
          </h2>
          {pagination && (
            <span className="shrink-0 rounded-full bg-white px-3 py-1 text-[11px] font-bold text-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
              총 {pagination.total_items}건
            </span>
          )}
        </div>

        {data.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
            {data.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <div className="rounded-3xl bg-white p-12 text-center text-sm text-slate-400 dark:bg-slate-900/60">
            아직 모아 온 콘텐츠가 없어요.
          </div>
        )}

        {pagination && pagination.total_pages > 1 && (
          <div className="flex items-center justify-center gap-3 pt-6">
            <PageButton
              href={`/news?view=content&page=${pagination.current_page - 1}`}
              disabled={!pagination.has_prev_page}
              direction="prev"
            />
            <span className="rounded-full bg-white px-4 py-2 text-sm font-bold tabular-nums text-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
              {pagination.current_page} / {pagination.total_pages}
            </span>
            <PageButton
              href={`/news?view=content&page=${pagination.current_page + 1}`}
              disabled={!pagination.has_next_page}
              direction="next"
            />
          </div>
        )}
      </section>
    </div>
  );
}

function PageButton({
  href,
  disabled,
  direction,
}: {
  href: string;
  disabled: boolean;
  direction: "prev" | "next";
}) {
  const Icon = direction === "prev" ? ChevronLeft : ChevronRight;
  const className = `flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
    disabled
      ? "cursor-not-allowed bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600"
      : "bg-slate-900 text-white hover:opacity-90 dark:bg-white dark:text-slate-900"
  }`;
  if (disabled) {
    return (
      <span className={className} aria-disabled>
        <Icon className="h-4 w-4" />
      </span>
    );
  }
  return (
    <Link
      href={href}
      className={className}
      aria-label={direction === "prev" ? "이전" : "다음"}
    >
      <Icon className="h-4 w-4" />
    </Link>
  );
}
