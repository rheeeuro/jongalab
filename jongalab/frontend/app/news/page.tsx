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
  title: "뉴스",
  description:
    "그 날의 종목 재료와 헤드라인, 그리고 유튜브·텔레그램 콘텐츠 분석.",
  // ?view=·?date=·?page= 변형은 기본 경로로 통합해 중복 색인을 방지한다.
  alternates: { canonical: "/news" },
};

export const dynamic = "force-dynamic";

type View = "news" | "content";

const STREAM_PAGE = 40;
const BUZZ_LIMIT = 15;
const CONTENT_PAGE = 12;

async function getMaterials(date: string): Promise<NewsMaterialRow[]> {
  const res = await apiFetch<{ success: boolean; data: NewsMaterialRow[] } | null>(
    `/api/news/materials?date=${date}`,
    null,
  );
  return res?.data ?? [];
}

async function getHeat(date: string): Promise<NewsHeatItem[]> {
  const res = await apiFetch<{ success: boolean; data: NewsHeatItem[] } | null>(
    `/api/news/heat?date=${date}&limit=${BUZZ_LIMIT}`,
    null,
  );
  return res?.data ?? [];
}

async function getStream(
  date: string,
): Promise<{ items: NewsStreamItem[]; total: number; hasMore: boolean }> {
  const res = await apiFetch<NewsStreamResponse | null>(
    `/api/news/stream?date=${date}&limit=${STREAM_PAGE}`,
    null,
  );
  return { items: res?.data ?? [], total: res?.total ?? 0, hasMore: Boolean(res?.has_more) };
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

/**
 * 뉴스 탭 — **뉴스**(기사 기반 재료)와 **콘텐츠**(유튜브·텔레그램 분석)를 세그먼트로 나눈다.
 * 둘 다 '어떤 재료가 돌고 있나'라는 같은 질문이지만 출처·시간축이 달라 한 화면에 쌓으면
 * 스크롤만 길어졌다. 시장 탭과 같은 방식이라 목적지(탭)는 늘지 않고 canonical 도 `/news` 하나다.
 *
 * 뉴스 뷰는 그 날의 뉴스판을 **요약 → 종목별 재료 → 원문 헤드라인** 순으로 보여준다.
 *
 * 2026-08-05 헤드라인 소스 교체. `NewsStream` 이 텔레그램 종합 속보 채널을 읽는 동안 주식과
 * 무관한 기사가 4.1% 섞여 있었다(`70대 남성 사망`→남성 004270 · `한화, 삼성 4-1 제압`→한화
 * 000880). 매처가 아니라 **모집단**이 원인이라 네이버 증권 섹션(`sec_news`)으로 갈아끼웠다.
 * 재료 목록·뉴스량 랭킹은 그대로 `news_mention` 을 읽는다 — 화면만 바뀌고 라벨·rule 표본은
 * 안 건드린다(sql/49).
 *
 * 2026-08-03 구조 재설계. 예전 화면은 오늘 유니버스 중 뉴스가 있는 종목만을 지속성 등급
 * 3그룹으로 나눈 카드 그리드였는데, 주식 정보 화면으로는 세 가지가 빠져 있었다.
 *   1) **시간축·원문이 없다** — 뉴스 탭인데 헤드라인이 한 줄도 없었다 → `NewsStream` 추가.
 *   2) **모수가 너무 좁다** — 실측 2026-08-03 뉴스 붙은 종목 131개 중 후보와 겹친 건 7개.
 *      후보 밖 종목은 `NewsBuzzRail`(뉴스량 랭킹)이 덮는다.
 *   3) **묶는 축이 사용자 축이 아니다** — 절반 이상이 '판정 보류'로 떨어지는 등급 그룹핑을
 *      **단일 목록 + 필터/정렬/검색**(`MaterialBoard`)으로 바꿨다.
 * 여기에 날짜 이동(`NewsDateNav`)과 요약 타일(`NewsSummaryStrip`)을 더해 "어느 날의 무엇을
 * 보고 있는지"를 첫 화면에서 알 수 있게 했다.
 *
 * ⚠️ 지속성 라벨은 여전히 **candidate rule 표본(관찰 전용·미검증)**이다. 예전 헤더의 4줄짜리
 * 면책 문단은 모바일 첫 화면을 다 먹었으므로 접이식 안내로 옮기되, 문구는 그대로 남긴다.
 *
 * 모바일 우선: 전부 1열로 흐르고, lg 부터 [본문 | 사이드 레일] 2열.
 */
export default async function NewsPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; date?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const view: View = sp.view === "content" ? "content" : "news";

  return (
    <main className="mx-auto max-w-7xl px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:pb-10">
      <header>
        <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
          <Newspaper className="h-4 w-4 text-emerald-500" />
          <span>오늘의 재료</span>
        </div>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
          뉴스
        </h1>
        <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
          기사에서 나온 종목 재료와, 유튜브·텔레그램 콘텐츠 분석을 나눠서 봅니다.
        </p>
      </header>

      <div className="mt-4">
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
      </div>

      <div className="mt-5">
        {view === "news" ? (
          <NewsView date={sp.date} />
        ) : (
          <ContentView page={Number(sp.page) || 1} />
        )}
      </div>
    </main>
  );
}

async function NewsView({ date: requestedDate }: { date?: string }) {
  const dates = await getReportDates();
  const requested =
    requestedDate && DATE_RE.test(requestedDate) ? requestedDate : null;
  // 기본은 '가장 최근 리포트일'이다. 오늘로 고정하면 휴장일·장 시작 전에 통째로 빈 화면이 된다.
  const date = requested ?? dates[0] ?? todayStr();

  const [rows, heat, stream] = await Promise.all([
    getMaterials(date),
    getHeat(date),
    getStream(date),
  ]);

  const isToday = date === todayStr();

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {isToday ? "오늘" : formatKoDate(date)}의 종목 재료와 수집 헤드라인
        </p>
        <NewsDateNav date={date} dates={dates} />
      </div>

      {/* 면책은 접이식으로 — 첫 화면을 먹지 않되 '미검증'은 닫힌 상태에서도 보이게 한다.
          details/summary(CSS-only)라 서버 컴포넌트를 유지한다. */}
      <details className="mt-3 rounded-2xl bg-white px-4 py-3 dark:bg-slate-900/60">
        <summary className="cursor-pointer list-none text-xs font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300">
          ⚠️ 재료 등급은 관찰 중 · 미검증입니다 — 어떻게 판정하나요?
        </summary>
        <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          뉴스가 있는 후보 종목의 재료를 AI가 읽고 <b>이어질 성질인지</b> 판정합니다. 다음 예정
          사건이 남고 수치가 확정되지 않았으면 &lsquo;연속&rsquo;, 수치가 확정되고 남은 일정이
          없으면 &lsquo;소진&rsquo;입니다. 재료를 특정할 수 없으면 억지로 채우지 않고 판정을
          보류합니다.
          <br />
          <span className="font-bold text-slate-400 dark:text-slate-500">
            이 등급은 매수 신호가 아니고 실매매에 개입하지 않습니다(성적만 기록 중).
          </span>
        </p>
      </details>

      <div className="mt-5 mb-6">
        <NewsSummaryStrip rows={rows} articleCount={stream.total} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-8">
        <div className="min-w-0 space-y-8">
          {rows.length === 0 ? (
            <p className="rounded-2xl bg-white p-6 text-center text-sm font-medium text-slate-400 dark:bg-slate-900/60">
              이 날 뉴스가 매칭된 후보 종목이 없습니다.
            </p>
          ) : (
            <MaterialBoard rows={rows} date={date} />
          )}

          <NewsStream
            date={date}
            initial={stream.items}
            total={stream.total}
            hasMore={stream.hasMore}
          />
        </div>

        <aside className="min-w-0 lg:sticky lg:top-20 lg:self-start">
          <NewsBuzzRail items={heat} />
        </aside>
      </div>
    </>
  );
}

/** 콘텐츠 뷰 — 예전 `/feed` 탭의 본문(언급 트리맵 + 페이지네이션 목록)을 그대로 옮겼다. */
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
            아직 수집된 콘텐츠가 없습니다.
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
