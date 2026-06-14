"use client";

import { MarketIndex } from "@/types";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { SlotNumber } from "./SlotNumber";

function formatPrice(price: number, symbol: string): string {
  if (symbol === "USDKRW=X") {
    return `₩${price.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (symbol === "BTC-USD") {
    return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return `${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function AnimatedMarketIndexCard({
  item,
  animate,
}: {
  item: MarketIndex;
  animate: boolean;
}) {
  if (item.price === null) {
    return (
      <div className="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/40">
        <p className="text-sm font-bold text-slate-500 dark:text-slate-400">{item.name}</p>
        <p className="mt-1 text-xs text-slate-400">데이터 없음</p>
      </div>
    );
  }

  const isUp = (item.change_percent ?? 0) > 0;
  const isDown = (item.change_percent ?? 0) < 0;

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const changeColor = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500 dark:text-slate-400";

  const priceStr = formatPrice(item.price, item.symbol);
  const changeStr = `${isUp ? "+" : ""}${item.change?.toFixed(2)}`;
  const pctStr = `(${isUp ? "+" : ""}${item.change_percent?.toFixed(2)}%)`;

  return (
    <div className="rounded-2xl bg-slate-50 p-4 transition-all hover:-translate-y-0.5 dark:bg-slate-800/40">
      <div className="flex items-center justify-between">
        <p className="truncate text-sm font-bold text-slate-500 dark:text-slate-400">
          {item.name}
        </p>
        <Icon className={`h-4 w-4 ${changeColor}`} />
      </div>
      <div className="mt-1.5 text-xl font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100">
        <SlotNumber value={priceStr} animate={animate} />
      </div>
      <div
        className={`mt-1 flex items-center gap-2 text-sm font-bold tabular-nums ${changeColor}`}
      >
        <SlotNumber value={changeStr} animate={animate} />
        <SlotNumber value={pctStr} animate={animate} />
      </div>
    </div>
  );
}
