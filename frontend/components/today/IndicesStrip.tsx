import { MarketIndex } from "@/types";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface Props {
  indices: {
    US: MarketIndex[];
    KR: MarketIndex[];
    COMMODITIES: MarketIndex[];
  } | null;
}

export function IndicesStrip({ indices }: Props) {
  if (!indices) return null;

  const items: MarketIndex[] = [];
  items.push(...(indices.US ?? []));
  items.push(...(indices.KR ?? []));
  items.push(...(indices.COMMODITIES ?? []));

  // 가격이 있는 것만 표시 + 최대 8개
  const visible = items.filter((i) => i.price !== null).slice(0, 8);
  if (!visible.length) return null;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          주요 지수
        </h2>
      </div>

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2.5 pb-1 sm:grid sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
          {visible.map((idx) => (
            <IndexChip key={idx.symbol} idx={idx} />
          ))}
        </div>
      </div>
    </section>
  );
}

function IndexChip({ idx }: { idx: MarketIndex }) {
  const isUp = (idx.change_percent ?? 0) > 0;
  const isDown = (idx.change_percent ?? 0) < 0;
  const tone = isUp
    ? "text-rose-600 dark:text-rose-400"
    : isDown
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";
  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const isKr =
    idx.symbol.endsWith(".KS") || idx.symbol.endsWith(".KQ");

  const priceStr =
    idx.price === null
      ? "-"
      : isKr
        ? idx.price.toLocaleString("ko-KR", { maximumFractionDigits: 0 })
        : idx.price.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          });

  return (
    <div className="min-w-[160px] shrink-0 rounded-2xl bg-white p-4 dark:bg-slate-900/60 sm:min-w-0">
      <p className="truncate text-xs font-bold text-slate-500 dark:text-slate-400">
        {idx.name}
      </p>
      <p className="mt-1.5 text-lg font-extrabold tabular-nums tracking-tight text-slate-900 dark:text-slate-100">
        {priceStr}
      </p>
      <p
        className={`mt-1 flex items-center gap-1 text-xs font-bold tabular-nums ${tone}`}
      >
        <Icon className="h-3 w-3" />
        {isUp ? "+" : ""}
        {idx.change_percent?.toFixed(2) ?? "0.00"}%
      </p>
    </div>
  );
}
