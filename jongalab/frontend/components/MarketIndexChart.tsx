"use client";

import { useState } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { CandlestickChart } from "@/components/CandlestickChart";
import type { HourlyCandleItem, MarketIndexHistory } from "@/types";

const RANGES = [
  { key: "1d", label: "1일" },
  { key: "5d", label: "5일" },
  { key: "1mo", label: "1개월" },
] as const;

type RangeKey = (typeof RANGES)[number]["key"];

function formatPrice(price: number, symbol: string): string {
  if (symbol === "USDKRW=X") {
    return `₩${price.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (symbol === "BTC-USD") {
    return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function MarketIndexChart({
  symbol,
  initialCandles,
}: {
  symbol: string;
  initialCandles: HourlyCandleItem[];
}) {
  const [range, setRange] = useState<RangeKey>("5d");
  const [candles, setCandles] = useState<HourlyCandleItem[]>(initialCandles);
  const [loading, setLoading] = useState(false);

  async function pick(next: RangeKey) {
    if (next === range || loading) return;
    setRange(next);
    setLoading(true);
    try {
      const res = await fetch(
        `/api/market-index-history/${encodeURIComponent(symbol)}?range=${next}`,
        { cache: "no-store" },
      );
      const data: MarketIndexHistory = await res.json();
      setCandles(data.candles ?? []);
    } catch {
      /* 실패 시 이전 데이터 유지 */
    } finally {
      setLoading(false);
    }
  }

  // 창 등락(첫 봉 시가 → 마지막 봉 종가) — 선택 구간 동안의 움직임.
  const first = candles[0];
  const last = candles.at(-1);
  const change = first && last ? last.close - first.open : null;
  const pct = change !== null && first?.open ? (change / first.open) * 100 : null;
  const isUp = (pct ?? 0) > 0;
  const isDown = (pct ?? 0) < 0;
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500 dark:text-slate-400";
  const hasExtended = candles.some((c) => c.extended);
  // 코스피200 선물은 yfinance 가 아니라 KIS(주간 분봉)+DB(야간 분봉)로 조립한다 —
  // 1일만 분봉이고 그 이상은 일봉이며, 흐린 봉의 의미도 프리/애프터가 아니라 야간세션이다.
  const isFutures = symbol === "K200NF" || symbol === "K200DF";
  const granularity = isFutures
    ? range === "1d"
      ? "1분봉 (야간세션 포함)"
      : "일봉 (주간·야간 합산)"
    : "분봉 (프리·애프터마켓 포함)";

  return (
    <div className="space-y-3">
      {/* 현재가 + 구간 등락 + 범위 토글 (모바일: 세로 스택 → sm: 한 줄) */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {last && (
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100">
              {formatPrice(last.close, symbol)}
            </span>
            {change !== null && pct !== null && (
              <span className={`flex items-center gap-1 text-sm font-bold tabular-nums ${changeColor}`}>
                <Icon className="h-4 w-4" />
                {isUp ? "+" : ""}
                {change.toFixed(2)} ({isUp ? "+" : ""}
                {pct.toFixed(2)}%)
              </span>
            )}
          </div>
        )}
        <div
          role="tablist"
          aria-label="차트 범위"
          className="inline-flex self-start rounded-full bg-slate-100 p-1 dark:bg-slate-800 sm:self-auto"
        >
          {RANGES.map((r) => (
            <button
              key={r.key}
              role="tab"
              aria-selected={range === r.key}
              onClick={() => pick(r.key)}
              disabled={loading}
              className={`min-w-[3rem] rounded-full px-3 py-1.5 text-sm font-bold transition-colors disabled:opacity-60 ${
                range === r.key
                  ? "bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className={loading ? "opacity-50 transition-opacity" : "transition-opacity"}>
        {candles.length > 0 ? (
          <CandlestickChart data={candles} fit />
        ) : (
          <p className="py-12 text-center text-sm text-slate-400">
            {isFutures
              ? "선물 가격을 가져오지 못했어요. 잠시 뒤에 다시 시도해 주세요."
              : "이 지표는 분 단위 차트를 제공하지 않아요."}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-slate-500 dark:text-slate-400">
        <span>{granularity}</span>
        {hasExtended && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-rose-300 dark:bg-rose-400/60" />
            {isFutures ? "흐린 봉 = 야간세션(18:00~05:00)" : "흐린 봉 = 정규장 밖(프리/애프터)"}
          </span>
        )}
      </div>
    </div>
  );
}
