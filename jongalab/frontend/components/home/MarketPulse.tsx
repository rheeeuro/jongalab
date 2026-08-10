import Link from "next/link";
import { MarketIndex, SectorReport } from "@/types";

/** 홈 상단 시장 스트립 — "오늘 시장이 어땠나"를 **추천 목록 위에서** 한 줄로 답한다.
 *
 * 예전에는 지수·섹터가 픽 카드 10장 **아래**에 있어 모바일에서 스크롤해야 보였다.
 * 위로 올리되 한 줄 높이(칩)로 묶어, 홈이 다시 종합 대시보드가 되지 않게 한다.
 *
 * ⚠️ 상한: **칩 한 줄**이다. 차트·필터·펼침을 붙이지 말 것 — 그 순간 추천이 아래로 밀린다.
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
  const topSectors = [...sectors].sort((a, b) => a.rank_no - b.rank_no).slice(0, 2);

  return (
    <section
      aria-label="오늘 시장"
      className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0"
    >
      <div className="flex items-stretch gap-2 pb-1">
        {indexSlot}
        {topSectors.map((s) => (
          <Chip
            key={s.thema_grp_cd}
            href="/market?view=sector"
            label={`주도섹터 ${s.rank_no}위`}
            value={s.thema_nm}
            pct={s.flu_rt}
          />
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
        <Chip
          key={i.symbol}
          href="/market"
          label={i.name}
          value={
            i.price?.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) ?? "—"
          }
          pct={i.change_percent}
        />
      ))}
    </>
  );
}

export function IndexChipsSkeleton() {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className={`${CHIP} pointer-events-none`}>
          <div className="h-3 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          <div className="mt-1.5 h-4 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          <div className="mt-1 h-3 w-10 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
        </div>
      ))}
    </>
  );
}

// 모바일은 고정폭 칩의 가로 스크롤, sm 이상은 남는 폭을 균등 분배해 KPI 줄이 된다.
const CHIP =
  "min-w-[104px] shrink-0 rounded-2xl bg-white px-3 py-2 sm:min-w-0 sm:flex-1 dark:bg-slate-900/60";

function pctTone(pct: number | null | undefined): string {
  if (pct == null) return "text-slate-400";
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-500";
}

function Chip({
  href,
  label,
  value,
  pct,
}: {
  href: string;
  label: string;
  value: string;
  pct: number | null | undefined;
}) {
  return (
    <Link
      href={href}
      className={`${CHIP} block transition-colors hover:bg-slate-50 dark:hover:bg-slate-900`}
    >
      <p className="truncate text-[10px] font-bold text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-extrabold tabular-nums text-slate-900 dark:text-slate-100">
        {value}
      </p>
      <p
        className={`truncate text-[11px] font-extrabold tabular-nums ${pctTone(pct)}`}
      >
        {pct == null ? "—" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`}
      </p>
    </Link>
  );
}
