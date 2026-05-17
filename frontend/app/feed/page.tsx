import { ContentAnalysis, PaginatedResponse } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Newspaper } from "lucide-react";

async function getContents(
  page: number,
  limit: number,
  market: string,
): Promise<PaginatedResponse<ContentAnalysis>> {
  return apiFetch(`/api/contents?page=${page}&limit=${limit}&market=${market}`, {
    success: false,
    data: [],
    pagination: null,
  });
}

export const dynamic = "force-dynamic";

export default async function FeedPage(props: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await props.searchParams;
  const market = (params?.market as string) || "ALL";
  const page = Number(params?.page) || 1;
  const limit = 12;

  const contentsRes = await getContents(page, limit, market);
  const data = contentsRes.data || [];
  const pagination = contentsRes.pagination;

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
        {/* 헤더 */}
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
              <Newspaper className="h-4 w-4 text-indigo-500" />
              <span>AI 분석 콘텐츠</span>
            </div>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
              지금 시장은
              <br />
              뭐라고 말할까?
            </h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              YouTube · Telegram 콘텐츠를 AI가 실시간 분석합니다.
            </p>
          </div>
          {pagination && (
            <span className="shrink-0 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
              총 {pagination.total_items}건
            </span>
          )}
        </div>

        {/* 콘텐츠 그리드 */}
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

        {/* 페이지네이션 */}
        {pagination && pagination.total_pages > 1 && (
          <div className="flex items-center justify-center gap-3 pt-4">
            <PageButton
              href={`/feed?market=${market}&page=${pagination.current_page - 1}`}
              disabled={!pagination.has_prev_page}
              direction="prev"
            />
            <span className="rounded-full bg-white px-4 py-2 text-sm font-bold tabular-nums text-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
              {pagination.current_page} / {pagination.total_pages}
            </span>
            <PageButton
              href={`/feed?market=${market}&page=${pagination.current_page + 1}`}
              disabled={!pagination.has_next_page}
              direction="next"
            />
          </div>
        )}
      </div>
    </main>
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
    <Link href={href} className={className} aria-label={direction === "prev" ? "이전" : "다음"}>
      <Icon className="h-4 w-4" />
    </Link>
  );
}
