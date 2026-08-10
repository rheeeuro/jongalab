import Link from "next/link";
import { Flame, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { MarketIndex, SectorReport } from "@/types";
import { Sparkline } from "@/components/Sparkline";
import { CARD, CARD_HOVER } from "@/lib/ui";

/** 홈 상단 시장 스트립 — "오늘 시장이 어땠나"를 **추천 목록 위에서** 한 줄로 답한다.
 *
 * 지수 칩은 시장 탭과 같은 언어를 쓴다: 카드 바닥에 깔린 스파크라인 + 추세 아이콘 + 등락률.
 * 숫자만 있는 칩은 "지금 값"만 말하고 흐름을 못 보여줘서, 아래 픽 카드들과 구분도 안 됐다.
 *
 * ⚠️ 상한: **칩 한 줄**이다. 큰 차트·필터·펼침을 붙이지 말 것 — 그 순간 추천이 아래로 밀린다.
 * 한 줄을 넘어서는 내용은 해당 탭(`/market`)에 둔다.
 */
export function MarketPulse({
  indexSlot,
  sectors,
}: {
  /** 지수 칩 — 외부 시세 API 라 느려서 페이지가 `Suspense` 로 감싸 넘긴다. */
  indexSlot: React.ReactNode;
  sectors: SectorReport[];
}) {
  const topSectors = [...sectors]
    .sort((a, b) => a.rank_no - b.rank_no)
    .slice(0, 2);

  return (
    <section
      aria-label="오늘 시장"
      className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:overflow-visible sm:px-0"
    >
      <div className="flex items-stretch gap-2">
        {indexSlot}
        {topSectors.map((s) => (
          <SectorChip key={s.thema_grp_cd} sector={s} />
        ))}
      </div>
    </section>
  );
}

/** 지수 칩 — 국내 2개(코스피·코스닥) + 미국 대표 1개.
 *
 * 각 배열의 앞에서 잘라 쓴다(백엔드가 대표 지수를 앞에 둔다). 국내를 먼저 두는 건
 * 이 사이트의 추천이 전부 한국 종목이기 때문이고, 환율·반도체지수 같은 나머지는
 * 칩 줄이 길어지지 않게 `/market` 에 남긴다.
 */
export function IndexChips({
  indices,
}: {
  indices: { US: MarketIndex[]; KR: MarketIndex[] } | null;
}) {
  const kr = (indices?.KR ?? []).filter((i) => i.price !== null).slice(0, 2);
  const us = (indices?.US ?? []).filter((i) => i.price !== null).slice(0, 1);
  const items = [...kr, ...us];
  if (!items.length) return null;

  return (
    <>
      {items.map((i) => (
        <IndexChip key={i.symbol} item={i} />
      ))}
    </>
  );
}

export function IndexChipsSkeleton() {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className={`${CHIP} ${CARD}`}>
          <div className="h-3 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          <div className="mt-1.5 h-4 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          <div className="mt-1.5 h-3 w-10 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
        </div>
      ))}
    </>
  );
}

// 모바일은 고정폭 칩의 가로 스크롤, sm 이상은 남는 폭을 균등 분배해 KPI 줄이 된다.
// 스파크라인이 들어가 예전(104px)보다 넓다 — 좁으면 선이 뭉개져 흐름이 안 읽힌다.
const CHIP =
  "relative min-w-[124px] shrink-0 overflow-hidden px-3 py-2.5 sm:min-w-0 sm:flex-1";

type Tone = "up" | "down" | "flat";

function toneOf(pct: number | null | undefined): Tone {
  if (pct == null || pct === 0) return "flat";
  return pct > 0 ? "up" : "down";
}

const TONE_TEXT: Record<Tone, string> = {
  up: "text-rose-600 dark:text-rose-400",
  down: "text-blue-600 dark:text-blue-400",
  flat: "text-slate-400 dark:text-slate-500",
};

function signed(pct: number | null | undefined): string {
  if (pct == null) return "—";
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function IndexChip({ item }: { item: MarketIndex }) {
  const tone = toneOf(item.change_percent);
  const Icon = tone === "up" ? TrendingUp : tone === "down" ? TrendingDown : Minus;
  const spark = item.sparkline ?? [];

  return (
    <Link href="/market" className={`${CHIP} ${CARD} ${CARD_HOVER} block`}>
      {spark.length >= 2 && (
        <Sparkline
          data={spark}
          tone={tone}
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 w-full"
        />
      )}
      {/* 스파크라인 위로 올리는 스택 컨텍스트 — 배경 선이 숫자를 덮지 않게 한다 */}
      <div className="relative">
        <div className="flex items-center gap-1">
          <p className="truncate text-[10px] font-bold text-slate-500 dark:text-slate-400">
            {item.name}
          </p>
          <Icon className={`ml-auto h-3 w-3 shrink-0 ${TONE_TEXT[tone]}`} />
        </div>
        <p className="mt-0.5 truncate text-sm font-extrabold tabular-nums text-slate-900 dark:text-slate-100">
          {item.price?.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) ??
            "—"}
        </p>
        <p
          className={`truncate text-[11px] font-extrabold tabular-nums ${TONE_TEXT[tone]}`}
        >
          {signed(item.change_percent)}
        </p>
      </div>
    </Link>
  );
}

/** 주도 섹터 칩 — 지수와 달리 시계열이 없어 스파크라인 자리에 순위를 둔다.
 *  같은 줄에 있지만 아이콘·순위 배지로 '지수가 아님'이 바로 보이게 한다. */
function SectorChip({ sector }: { sector: SectorReport }) {
  const tone = toneOf(sector.flu_rt);

  return (
    <Link
      href="/market?view=sector"
      className={`${CHIP} ${CARD} ${CARD_HOVER} block`}
    >
      <div className="flex items-center gap-1">
        <Flame className="h-3 w-3 shrink-0 text-orange-500" />
        <p className="truncate text-[10px] font-bold text-slate-500 dark:text-slate-400">
          주도섹터
        </p>
        <span className="ml-auto shrink-0 rounded-full bg-orange-100 px-1.5 text-[10px] font-extrabold text-orange-600 dark:bg-orange-950/40 dark:text-orange-400">
          {sector.rank_no}위
        </span>
      </div>
      <p className="mt-0.5 truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
        {sector.thema_nm}
      </p>
      <p
        className={`truncate text-[11px] font-extrabold tabular-nums ${TONE_TEXT[tone]}`}
      >
        {signed(sector.flu_rt)}
        <span className="ml-1 font-bold text-slate-400 dark:text-slate-500">
          {sector.stk_num}종목
        </span>
      </p>
    </Link>
  );
}
