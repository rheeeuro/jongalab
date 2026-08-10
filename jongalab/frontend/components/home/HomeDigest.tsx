import Link from "next/link";
import { ChevronRight, Flame, LineChart, Newspaper } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { MarketIndex, NewsHeatItem, SectorReport } from "@/types";

/** 홈 하단 요약 — 추천을 본 뒤 "오늘 시장은 어땠나"를 훑는 자리다.
 *
 * ⚠️ 여기 있는 것은 전부 **각 탭의 압축본**이다. 카드·차트·필터를 붙이지 말 것 —
 * 홈이 다시 종합 대시보드가 되면 추천이 묻힌다. 한 줄 가로 스크롤을 넘어서면
 * 그건 해당 탭(`/market`·`/news`)에 둘 내용이다.
 */
function DigestSection({
  icon: Icon,
  title,
  href,
  linkLabel,
  children,
}: {
  icon: LucideIcon;
  title: string;
  href: string;
  linkLabel: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-1.5">
        <Icon className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
        <h2 className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
          {title}
        </h2>
        <Link
          href={href}
          className="ml-auto inline-flex shrink-0 items-center gap-0.5 text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
        >
          {linkLabel}
          <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
      {/* 모바일은 가로 스크롤 한 줄, sm 이상은 그리드로 펼친다 */}
      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0">
        {children}
      </div>
    </section>
  );
}

function pctTone(pct: number | null | undefined): string {
  if (pct == null) return "text-slate-400";
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-500";
}

function signed(pct: number, digits = 2): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

const ROW = "flex gap-2 pb-1 sm:grid sm:grid-cols-3 sm:gap-2.5 lg:grid-cols-5";
const CHIP =
  "min-w-[136px] shrink-0 rounded-2xl bg-white px-3 py-2.5 sm:min-w-0 dark:bg-slate-900/60";

export function IndexDigest({
  indices,
}: {
  indices: { US: MarketIndex[]; KR: MarketIndex[] } | null;
}) {
  // 국내 지수를 먼저 — 이 사이트의 추천은 전부 한국 종목이다.
  const items = [...(indices?.KR ?? []), ...(indices?.US ?? [])]
    .filter((i) => i.price !== null)
    .slice(0, 5);
  if (!items.length) return null;

  return (
    <DigestSection
      icon={LineChart}
      title="주요 지수"
      href="/market"
      linkLabel="시장"
    >
      <div className={ROW}>
        {items.map((i) => (
          <div key={i.symbol} className={CHIP}>
            <p className="truncate text-[11px] font-bold text-slate-500 dark:text-slate-400">
              {i.name}
            </p>
            <p className="mt-0.5 truncate text-sm font-extrabold tabular-nums text-slate-900 dark:text-slate-100">
              {i.price?.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}
            </p>
            <p
              className={`text-[11px] font-extrabold tabular-nums ${pctTone(i.change_percent)}`}
            >
              {i.change_percent == null ? "—" : signed(i.change_percent)}
            </p>
          </div>
        ))}
      </div>
    </DigestSection>
  );
}

export function IndexDigestSkeleton() {
  return (
    <DigestSection
      icon={LineChart}
      title="주요 지수"
      href="/market"
      linkLabel="시장"
    >
      <div className={ROW}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className={CHIP}>
            <div className="h-3 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
            <div className="mt-1.5 h-4 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
            <div className="mt-1 h-3 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          </div>
        ))}
      </div>
    </DigestSection>
  );
}

export function SectorDigest({ sectors }: { sectors: SectorReport[] }) {
  const top = [...sectors].sort((a, b) => a.rank_no - b.rank_no).slice(0, 5);
  if (!top.length) return null;

  return (
    <DigestSection
      icon={Flame}
      title="주도 섹터"
      href="/market?view=sector"
      linkLabel="섹터 전체"
    >
      <div className={ROW}>
        {top.map((s) => (
          <div key={s.thema_grp_cd} className={CHIP}>
            <p className="truncate text-[11px] font-bold text-slate-500 dark:text-slate-400">
              {s.rank_no}위 · {s.stk_num}종목
            </p>
            <p className="mt-0.5 truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
              {s.thema_nm}
            </p>
            <p
              className={`text-[11px] font-extrabold tabular-nums ${pctTone(s.flu_rt)}`}
            >
              {signed(s.flu_rt)}
            </p>
          </div>
        ))}
      </div>
    </DigestSection>
  );
}

export function NewsDigest({
  items,
  date,
}: {
  items: NewsHeatItem[];
  date: string;
}) {
  const top = items.slice(0, 5);
  if (!top.length) return null;

  return (
    <DigestSection
      icon={Newspaper}
      title="뉴스가 몰린 종목"
      href={`/news?date=${date}`}
      linkLabel="뉴스"
    >
      <div className={ROW}>
        {top.map((n) => (
          <Link
            key={n.ticker}
            href={`/stocks/${n.ticker}`}
            className={`${CHIP} block transition-all hover:-translate-y-0.5 hover:shadow-md`}
          >
            <p className="truncate text-[11px] font-bold text-slate-500 dark:text-slate-400">
              기사 {n.mention_count}건
              {n.in_universe === 1 && (
                <span className="ml-1 rounded-full bg-indigo-100 px-1 text-[10px] font-extrabold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                  후보
                </span>
              )}
            </p>
            <p className="mt-0.5 truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
              {n.company_name || n.ticker}
            </p>
            {/* 배수(자기 기저 대비)를 쓴다 — 건수 정렬은 사실상 시총 랭킹이 된다 */}
            <p className="truncate text-[11px] font-extrabold text-slate-500 tabular-nums dark:text-slate-400">
              평소의 {(n.surprise ?? 1).toFixed(1)}배
            </p>
          </Link>
        ))}
      </div>
    </DigestSection>
  );
}
