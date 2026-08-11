import Link from "next/link";
import { ChevronRight, Flame } from "lucide-react";
import { MarketIndex, SectorReport } from "@/types";
import { Sparkline } from "@/components/Sparkline";
import { CARD, CARD_HOVER } from "@/lib/ui";

/** 홈 상단 시장 스트립 — "오늘 시장이 어땠나"를 **추천 목록 위에서** 두 카드로 답한다.
 *
 * 성격이 다른 두 종류를 **각자의 카드**에 넣는다: 지수(가격+등락)와 주도섹터(순위+등락)는
 * 축이 달라, 같은 모양의 칩 5개로 늘어놓으면 눈이 다섯을 한 종류로 읽고 `주도섹터` 라벨도
 * 두 번 반복된다(예전 구조). 라벨은 카드당 한 번만 두고, 각 카드 이름 줄이 그 뜻을 낸다.
 *
 * **카드 안쪽은 가로(열) 배치다.** 카드가 가로로 길어서 항목을 세로로 쌓으면 오른쪽 폭이
 * 통째로 남고 카드만 길어진다(2026-08-11 2차 실패). 열 하나가 항목 하나이고, 열 안에서만
 * `식별 → 주값 → 등락률` 3줄로 읽힌다(두 카드가 같은 리듬을 쓴다).
 *
 * ⚠️ 상한: **카드 2장**이다. 큰 차트·필터·펼침을 붙이지 말 것 — 그 순간 추천이 아래로 밀린다.
 * 넘어서는 내용은 해당 탭(`/market`)에 둔다.
 */
export function MarketPulse({
  indexSlot,
  sectors,
  pickCodes,
}: {
  /** 지수 카드 — 외부 시세 API 라 느려서 페이지가 `Suspense` 로 감싸 넘긴다. */
  indexSlot: React.ReactNode;
  sectors: SectorReport[];
  /** 오늘 추천 종목코드 — 주도섹터와 겹치는 수를 세어 "이 줄이 픽과 무슨 상관인지" 답한다. */
  pickCodes: string[];
}) {
  const topSectors = [...sectors]
    .sort((a, b) => a.rank_no - b.rank_no)
    .slice(0, 2);

  return (
    <section
      aria-label="오늘 시장"
      // 모바일은 카드가 각자 전체 폭을 써야 안쪽 열(지수 3 / 섹터 2)이 뭉개지지 않는다.
      // `sm` 이상에서 나란히 놓고, 열이 하나 더 많은 지수 카드에 3:2 로 폭을 더 준다.
      className={`grid gap-2 sm:gap-3 ${
        topSectors.length
          ? "grid-cols-1 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
          : "grid-cols-1"
      }`}
    >
      {indexSlot}
      {topSectors.length > 0 && (
        <SectorCard sectors={topSectors} pickCodes={pickCodes} />
      )}
    </section>
  );
}

/** 두 카드의 공통 껍데기 — 이름 줄(+ 곁말) 한 줄 + 아래 가로 열 그리드.
 *  곁말은 라벨 옆에 붙인다: 카드 아래에 각주로 한 줄 더 두면 두 카드 높이가 어긋난다. */
function PulseCard({
  href,
  label,
  icon,
  note,
  children,
}: {
  href: string;
  label: string;
  icon?: React.ReactNode;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`group flex h-full flex-col px-3 py-2.5 ${CARD} ${CARD_HOVER}`}
    >
      <div className="flex items-center gap-1">
        {icon}
        <p className="shrink-0 text-[10px] font-extrabold tracking-wide text-slate-400 uppercase dark:text-slate-500">
          {label}
        </p>
        {note && (
          <p className="truncate text-[10px] font-semibold text-slate-400 dark:text-slate-500">
            · {note}
          </p>
        )}
        <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600" />
      </div>
      <div className="mt-1.5 flex-1">{children}</div>
    </Link>
  );
}

/** 지수 카드 — 국내 2개(코스피·코스닥) + 미국 대표 1개를 3열로.
 *
 * 각 배열의 앞에서 잘라 쓴다(백엔드가 대표 지수를 앞에 둔다). 국내를 먼저 두는 건
 * 이 사이트의 추천이 전부 한국 종목이기 때문이고, 환율·반도체지수 같은 나머지는
 * 열이 늘어나지 않게 `/market` 에 남긴다.
 */
export function IndexCard({
  indices,
}: {
  indices: { US: MarketIndex[]; KR: MarketIndex[] } | null;
}) {
  const kr = (indices?.KR ?? []).filter((i) => i.price !== null).slice(0, 2);
  const us = (indices?.US ?? []).filter((i) => i.price !== null).slice(0, 1);
  const items = [...kr, ...us];

  return (
    <PulseCard href="/market" label="시장">
      {items.length ? (
        <div className="grid grid-cols-3 gap-2 sm:gap-3">
          {items.map((i) => (
            <IndexCol key={i.symbol} item={i} />
          ))}
        </div>
      ) : (
        <p className="text-[11px] font-semibold text-slate-400 dark:text-slate-500">
          시세 준비 중
        </p>
      )}
    </PulseCard>
  );
}

export function IndexCardSkeleton() {
  return (
    <PulseCard href="/market" label="시장">
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i}>
            <div className="h-3 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
            <div className="mt-1.5 h-4 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
            <div className="mt-1.5 h-3 w-10 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
          </div>
        ))}
      </div>
    </PulseCard>
  );
}

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

/** 지수 한 열 — `이름 / 지수값 / 등락률`, 아래 절반에 스파크라인을 깐다.
 *  스파크라인은 시장 탭과 같은 언어다 — 숫자만 있으면 '지금 값'만 말하고 흐름이 안 보인다. */
function IndexCol({ item }: { item: MarketIndex }) {
  const tone = toneOf(item.change_percent);
  const spark = item.sparkline ?? [];

  return (
    <div className="relative min-w-0 overflow-hidden">
      {spark.length >= 2 && (
        <Sparkline
          data={spark}
          tone={tone}
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 w-full"
        />
      )}
      {/* 스파크라인 위로 올리는 스택 컨텍스트 — 배경 선이 숫자를 덮지 않게 한다 */}
      <div className="relative">
        <p className="truncate text-[10px] font-bold text-slate-500 dark:text-slate-400">
          {item.name}
        </p>
        <p className="mt-0.5 truncate text-sm font-extrabold text-slate-900 tabular-nums dark:text-slate-100">
          {item.price?.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) ??
            "—"}
        </p>
        <p
          className={`truncate text-[11px] font-extrabold tabular-nums ${TONE_TEXT[tone]}`}
        >
          {signed(item.change_percent)}
        </p>
      </div>
    </div>
  );
}

/** 주도섹터 카드 — 상위 2개를 2열로. 열 안쪽 3줄은 지수 열과 같은 리듬이다
 *  (`순위 / 테마명 / 등락률+종목수`). 시계열이 없어 스파크라인 자리는 비운다.
 *
 * 이름 줄의 곁말은 이 카드가 **추천과 무슨 상관인지**를 답한다(겹치는 픽 수). 겹침이 없으면
 * 그 사실을 그대로 적는다 — 비워 두면 '집계 전'과 구분되지 않는다.
 * 테마 구성종목 코드는 `005930_AL` 같은 접미사가 붙어 오므로 `_` 앞만 비교한다.
 */
function SectorCard({
  sectors,
  pickCodes,
}: {
  sectors: SectorReport[];
  pickCodes: string[];
}) {
  const picks = new Set(pickCodes);
  const matched = new Set(
    sectors.flatMap((s) =>
      (s.stocks ?? [])
        .map((st) => st.stk_cd?.split("_")[0])
        .filter((code) => code && picks.has(code)),
    ),
  );

  return (
    <PulseCard
      href="/market?view=sector"
      label="주도섹터"
      icon={<Flame className="h-3 w-3 shrink-0 text-orange-500" />}
      note={
        matched.size > 0 ? `추천 ${matched.size}종목 포함` : "추천과 겹침 없음"
      }
    >
      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        {sectors.map((s) => {
          const tone = toneOf(s.flu_rt);
          return (
            <div key={s.thema_grp_cd} className="min-w-0">
              <p>
                <span className="inline-block rounded-full bg-orange-100 px-1.5 text-[10px] font-extrabold text-orange-600 tabular-nums dark:bg-orange-950/40 dark:text-orange-400">
                  {s.rank_no}위
                </span>
              </p>
              <p className="mt-0.5 truncate text-sm font-extrabold text-slate-900 dark:text-slate-100">
                {s.thema_nm}
              </p>
              <p
                className={`truncate text-[11px] font-extrabold tabular-nums ${TONE_TEXT[tone]}`}
              >
                {signed(s.flu_rt)}
                <span className="ml-1 font-bold text-slate-400 dark:text-slate-500">
                  {s.stk_num}종목
                </span>
              </p>
            </div>
          );
        })}
      </div>
    </PulseCard>
  );
}
