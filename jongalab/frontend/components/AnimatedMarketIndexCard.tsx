"use client";

import Link from "next/link";
import { MarketIndex } from "@/types";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { SlotNumber } from "./SlotNumber";
import { Sparkline } from "./Sparkline";

function formatPrice(price: number, symbol: string): string {
  if (symbol === "USDKRW=X") {
    return `₩${price.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (symbol === "BTC-USD") {
    return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return `${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 카드 주값으로 쓸 **가장 최신 세션** — 프리/애프터 시세가 있으면 그쪽이 정규장보다 나중이다.
 *
 * 정규장 중(`REGULAR`)에는 그날 아침 프리마켓 값이 남아 올 수 있어 무시한다(그땐 정규장이 최신).
 * 장 밖 등락률(`extended_percent`)은 정규장 종가 대비라, 정규장 종가·등락은 아래 줄에 따로 남긴다.
 */
function latestQuote(item: MarketIndex) {
  const regular = {
    price: item.price!,
    change: item.change,
    percent: item.change_percent,
    sessionLabel: null as string | null,
    regularLine: null as string | null,
  };
  const state = item.market_state ?? "";
  if (
    item.extended_price == null ||
    item.extended_percent == null ||
    state.startsWith("REGULAR")
  ) {
    return regular;
  }
  const sessionLabel = state.startsWith("PRE")
    ? "프리장"
    : state.startsWith("POST")
    ? "애프터장"
    : "시간외";
  const regularPct = item.change_percent;
  return {
    price: item.extended_price,
    change: item.extended_price - item.price!,
    percent: item.extended_percent,
    sessionLabel,
    regularLine: `정규장 ${formatPrice(item.price!, item.symbol)}${
      regularPct != null
        ? ` · ${regularPct > 0 ? "+" : ""}${regularPct.toFixed(2)}%`
        : ""
    }`,
  };
}

export function AnimatedMarketIndexCard({
  item,
  animate,
}: {
  item: MarketIndex;
  animate: boolean;
}) {
  const href = `/market/${encodeURIComponent(item.symbol)}`;

  if (item.price === null) {
    return (
      <Link
        href={href}
        className="block rounded-2xl bg-slate-50 p-4 transition-all hover:-translate-y-0.5 dark:bg-slate-800/40"
      >
        <p className="text-sm font-bold text-slate-500 dark:text-slate-400">{item.name}</p>
        <p className="mt-1 text-xs text-slate-400">데이터 없음</p>
      </Link>
    );
  }

  const quote = latestQuote(item);
  const isUp = (quote.percent ?? 0) > 0;
  const isDown = (quote.percent ?? 0) < 0;

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500 dark:text-slate-400";

  const priceStr = formatPrice(quote.price, item.symbol);
  const changeStr = `${isUp ? "+" : ""}${quote.change?.toFixed(2)}`;
  const pctStr = `(${isUp ? "+" : ""}${quote.percent?.toFixed(2)}%)`;

  const tone: "up" | "down" | "flat" = isUp ? "up" : isDown ? "down" : "flat";
  const hasSpark = (item.sparkline?.length ?? 0) >= 2;

  return (
    <Link
      href={href}
      className="relative block overflow-hidden rounded-2xl bg-slate-50 p-4 transition-all hover:-translate-y-0.5 dark:bg-slate-800/40"
    >
      {hasSpark && (
        <Sparkline
          data={item.sparkline!}
          tone={tone}
          className="pointer-events-none absolute inset-x-0 bottom-0 h-2/3 w-full"
        />
      )}
      <div className="relative">
        <div className="flex items-center justify-between gap-1">
          <p className="truncate text-sm font-bold text-slate-500 dark:text-slate-400">
            {item.name}
          </p>
          <Icon className={`h-4 w-4 shrink-0 ${changeColor}`} />
        </div>
        {/* 세션 배지는 주값 옆에 둔다 — 아래 등락 줄은 모바일 폭(≈375px)에서 이미 꽉 찬다. */}
        <div className="mt-1.5 flex items-baseline gap-1.5 text-xl font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100">
          <SlotNumber value={priceStr} animate={animate} />
          {quote.sessionLabel && (
            <span className="shrink-0 rounded-full bg-slate-200/80 px-1.5 py-px text-[10px] font-extrabold tracking-normal text-slate-600 dark:bg-slate-700/70 dark:text-slate-300">
              {quote.sessionLabel}
            </span>
          )}
        </div>
        <div
          className={`mt-1 flex items-center gap-2 text-sm font-bold tabular-nums ${changeColor}`}
        >
          <SlotNumber value={changeStr} animate={animate} />
          <SlotNumber value={pctStr} animate={animate} />
        </div>
        {quote.regularLine && (
          <p className="mt-0.5 truncate text-[10px] font-semibold tabular-nums text-slate-400 dark:text-slate-500">
            {quote.regularLine}
          </p>
        )}
      </div>
    </Link>
  );
}
