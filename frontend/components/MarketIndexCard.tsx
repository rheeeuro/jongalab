import { MarketIndex } from "@/types";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

function formatPrice(price: number, symbol: string): string {
  if (symbol === "USDKRW=X") {
    return `₩${price.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (symbol === "BTC-USD") {
    return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return `${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function MarketIndexCard({ item }: { item: MarketIndex }) {
  if (item.price === null) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-sm font-medium text-slate-500">{item.name}</p>
        <p className="mt-1 text-xs text-slate-400">데이터 없음</p>
      </div>
    );
  }

  const isUp = (item.change_percent ?? 0) > 0;
  const isDown = (item.change_percent ?? 0) < 0;

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const changeColor = isUp
    ? "text-red-600 dark:text-red-400"
    : isDown
    ? "text-blue-600 dark:text-blue-400"
    : "text-slate-500 dark:text-slate-400";

  const bgAccent = isUp
    ? "border-red-100 dark:border-red-900/40"
    : isDown
    ? "border-blue-100 dark:border-blue-900/40"
    : "border-slate-200 dark:border-slate-800";

  return (
    <div
      className={`rounded-xl border bg-white p-4 transition-shadow hover:shadow-md dark:bg-slate-900 ${bgAccent}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
          {item.name}
        </p>
        <Icon className={`h-4 w-4 ${changeColor}`} />
      </div>
      <p className="mt-1 text-xl font-bold text-slate-900 dark:text-slate-100">
        {formatPrice(item.price, item.symbol)}
      </p>
      <div className={`mt-1 flex items-center gap-2 text-sm font-semibold ${changeColor}`}>
        <span>
          {isUp ? "+" : ""}
          {item.change?.toFixed(2)}
        </span>
        <span>
          ({isUp ? "+" : ""}
          {item.change_percent?.toFixed(2)}%)
        </span>
      </div>
    </div>
  );
}
