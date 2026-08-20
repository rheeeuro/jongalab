"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ExternalLink, Loader2, Newspaper, Search, X } from "lucide-react";
import { NewsStreamItem, NewsStreamResponse } from "@/types";
import { splitHeadlineMeta } from "@/lib/news";

const PAGE_SIZE = 40;

/**
 * 헤드라인 스트림 — 그 날 수집된 기사를 최신순으로 흘려 준다.
 *
 * 하루 1,000건대 파이어호스가 화면을 덮지 않도록 네 가지를 건다:
 *   1) **시세 기사를 기본으로 숨긴다** — "급등/상한가/특징주" 류가 다섯 중 하나꼴이다. 판별은
 *      후속 재료 채점과 같은 함수(`is_price_report`)라 화면과 채점의 기준이 갈리지 않는다.
 *   2) **큐레이션 계층 아래에 둔다** — 요약·재료 목록을 먼저 보고 원하면 원문으로 내려간다.
 *   3) **제목 검색·종목 필터** — 545건을 '더 보기'로만 훑는 것 외에 방법이 없으면 안 본다.
 *   4) **페이지당 40건씩만** 받고 나머지는 '더 보기'로 미룬다.
 *
 * ⚠️ **거르기·세기는 전부 서버가 한다**(`/api/news/stream` 의 `hide_price`·`q`·`ticker`).
 * 받은 페이지에서 화면이 걸러내면 헤더 총계·'더 보기' 카운터·실제 표시 건수가 서로 다른
 * 수가 된다(점검 전 실측: 545 / 40 / 28). `total` 은 항상 **지금 조건으로 나열되는 수**다.
 *
 * 소스는 **네이버 증권 섹션 기사**(`sec_news`)다. 종합 속보 채널을 모집단으로 쓰면 주식과
 * 무관한 기사가 섞인다(매처가 아니라 모집단 문제 — docs/history/news-pipeline.md).
 * 종목 칩(`stocks`)이 없는 기사가 많은 건 정상이다 — 시황·환율·정책 기사가 원래 그렇다.
 *
 * 모바일 우선: 1열, 시각은 제목 위 메타 줄에(좌측 시각 컬럼은 375px 에서 제목 폭을 먹는다).
 */
export function NewsStream({
  date,
  initial,
  total: initialTotal,
  priceTotal,
  hasMore: initialHasMore,
  ticker,
  tickerLabel,
  clearTickerHref,
}: {
  date: string;
  initial: NewsStreamItem[];
  total: number;
  /** 숨긴 시세 기사 수 (토글 라벨) */
  priceTotal: number;
  hasMore: boolean;
  /** 종목 칩 필터 — 재료 목록에서 '이 종목 기사' 로 넘어온 경우 */
  ticker?: string;
  tickerLabel?: string;
  clearTickerHref?: string;
}) {
  const [items, setItems] = useState(initial);
  const [total, setTotal] = useState(initialTotal);
  const [priceCount, setPriceCount] = useState(priceTotal);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [loading, setLoading] = useState(false);
  const [hidePrice, setHidePrice] = useState(true);
  const [failed, setFailed] = useState(false);
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setApplied(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const fetchPage = useCallback(
    async (offset: number) => {
      const qs = new URLSearchParams({
        date,
        limit: String(PAGE_SIZE),
        offset: String(offset),
        hide_price: hidePrice ? "1" : "0",
      });
      if (applied) qs.set("q", applied);
      if (ticker) qs.set("ticker", ticker);
      const res = await fetch(`/api/news/stream?${qs}`);
      if (!res.ok) throw new Error(String(res.status));
      return (await res.json()) as NewsStreamResponse;
    },
    [date, hidePrice, applied, ticker],
  );

  // 조건이 바뀌면 목록을 처음부터 다시 받는다. 서버 렌더로 이미 받아 둔 첫 상태
  // (시세 숨김 · 검색어 없음)에서는 돌지 않는다.
  const isFirstRun = useRef(true);
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    fetchPage(0)
      .then((json) => {
        if (cancelled) return;
        setItems(json.data ?? []);
        setTotal(json.total ?? 0);
        setPriceCount(json.price_total ?? 0);
        setHasMore(Boolean(json.has_more));
      })
      .catch(() => !cancelled && setFailed(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [fetchPage]);

  async function loadMore() {
    setLoading(true);
    setFailed(false);
    try {
      const json = await fetchPage(items.length);
      setItems((prev) => [...prev, ...(json.data ?? [])]);
      setHasMore(Boolean(json.has_more));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="headlines" className="scroll-mt-20">
      <div className="mb-3 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-lg">
          <Newspaper className="h-4.5 w-4.5 text-emerald-500" />
          헤드라인
          <span className="text-xs font-bold text-slate-400 tabular-nums">{total}건</span>
        </h2>
        <button
          type="button"
          onClick={() => setHidePrice((v) => !v)}
          className="shrink-0 rounded-full px-2.5 py-1.5 text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
        >
          {hidePrice
            ? `시세 기사 보기${priceCount ? ` (${priceCount})` : ""}`
            : "시세 기사 숨기기"}
        </button>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label className="relative flex min-w-0 flex-1 items-center">
          <Search className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="제목으로 기사 찾기"
            className="h-10 w-full rounded-full bg-white pl-9 pr-3 text-sm font-medium text-slate-900 outline-none ring-1 ring-transparent transition focus:ring-emerald-400 dark:bg-slate-900/60 dark:text-slate-100"
          />
        </label>
        {ticker && (
          <>
            <Link
              href={clearTickerHref ?? "#headlines"}
              className="flex shrink-0 items-center gap-1 rounded-full bg-slate-900 px-3 py-2 text-xs font-bold text-white dark:bg-white dark:text-slate-900"
            >
              {tickerLabel ?? ticker} 기사만
              <X className="h-3.5 w-3.5" />
            </Link>
            {/* 필터 칩은 '해제' 링크라 종목 페이지로 갈 자리가 없다 — 옆에 따로 둔다. */}
            <Link
              href={`/stocks/${ticker}`}
              className="flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              종목 페이지
            </Link>
          </>
        )}
      </div>

      <div className="overflow-hidden rounded-2xl bg-white dark:bg-slate-900/60">
        {items.length === 0 ? (
          <p className="p-6 text-center text-sm font-medium text-slate-400">
            {applied || ticker
              ? "조건에 맞는 기사가 없어요."
              : "이 날 모아 온 기사가 없어요."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {items.map((it, idx) => (
              <li key={`${it.source_url ?? it.headline}-${idx}`}>
                <StreamRow item={it} />
              </li>
            ))}
          </ul>
        )}

        {hasMore && (
          <div className="border-t border-slate-100 p-2 dark:border-slate-800">
            <button
              type="button"
              onClick={loadMore}
              disabled={loading}
              className="flex h-10 w-full items-center justify-center gap-1.5 rounded-xl text-sm font-bold text-slate-500 transition-colors hover:bg-slate-50 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-800/60"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {failed ? "다시 시도" : `더 보기 (${items.length}/${total})`}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function StreamRow({ item }: { item: NewsStreamItem }) {
  const { publisher, title, url } = splitHeadlineMeta(item.headline, item.channel_name);
  const href = url ?? item.source_url;
  const time = formatTime(item.created_at);

  return (
    <div className={`px-4 py-3 ${item.is_price_report ? "opacity-60" : ""}`}>
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
        {time && <span className="tabular-nums">{time}</span>}
        {publisher && (
          <>
            <span aria-hidden>·</span>
            <span className="truncate">{publisher}</span>
          </>
        )}
        {item.is_price_report && (
          <span className="shrink-0 rounded-full bg-slate-100 px-1.5 text-[10px] font-bold text-slate-400 dark:bg-slate-800">
            시세
          </span>
        )}
      </div>

      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-0.5 flex items-start gap-1.5 group"
        >
          <p className="min-w-0 flex-1 break-words text-sm font-semibold leading-snug text-slate-800 group-hover:text-emerald-600 dark:text-slate-200 dark:group-hover:text-emerald-400">
            {title}
          </p>
          <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300 dark:text-slate-600" />
        </a>
      ) : (
        <p className="mt-0.5 break-words text-sm font-semibold leading-snug text-slate-800 dark:text-slate-200">
          {title}
        </p>
      )}

      {item.stocks.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {item.stocks.map((s) => (
            <Link
              key={s.ticker}
              href={`/stocks/${s.ticker}`}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600 transition-colors hover:bg-emerald-100 hover:text-emerald-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-emerald-950/50 dark:hover:text-emerald-400"
            >
              {s.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * "2026-08-03T14:35:21" → "14:35".
 *
 * `new Date(...)` 로 파싱하지 않는다 — `created_at` 은 타임존 표기가 없는 **KST 벽시계 값**이라
 * Date 로 돌리면 브라우저 로케일에 따라 해석이 갈리고, 여기는 클라이언트 컴포넌트라 서버
 * 렌더와 하이드레이션이 어긋난다. 문자열을 그대로 자르는 쪽이 결정적이고 정확하다.
 */
function formatTime(iso: string | null): string {
  const m = (iso ?? "").match(/T(\d{2}:\d{2})/);
  return m ? m[1] : "";
}
