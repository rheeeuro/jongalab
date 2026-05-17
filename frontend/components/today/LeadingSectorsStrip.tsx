import Link from "next/link";
import { SectorReport } from "@/types";
import { ArrowRight, Flame } from "lucide-react";

interface Props {
  sectors: SectorReport[];
}

const RANK_TONE = [
  "bg-gradient-to-br from-rose-500 to-orange-500",
  "bg-gradient-to-br from-orange-500 to-amber-500",
  "bg-gradient-to-br from-amber-500 to-yellow-500",
  "bg-gradient-to-br from-emerald-500 to-teal-500",
  "bg-gradient-to-br from-cyan-500 to-sky-500",
  "bg-gradient-to-br from-blue-500 to-indigo-500",
];

export function LeadingSectorsStrip({ sectors }: Props) {
  const top = sectors.slice(0, 6);
  if (!top.length) return null;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          <Flame className="h-5 w-5 text-orange-500" />
          리딩 섹터
        </h2>
        <Link
          href="/sectors"
          className="inline-flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          모두 보기
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2.5 pb-1 sm:grid sm:grid-cols-2 sm:gap-3 lg:grid-cols-3">
          {top.map((s, idx) => (
            <SectorChip key={s.thema_grp_cd} sector={s} idx={idx} />
          ))}
        </div>
      </div>
    </section>
  );
}

function SectorChip({ sector: s, idx }: { sector: SectorReport; idx: number }) {
  const isUp = s.flu_rt > 0;
  const tone = isUp
    ? "text-rose-600 dark:text-rose-400"
    : s.flu_rt < 0
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500";

  return (
    <div className="min-w-[220px] shrink-0 overflow-hidden rounded-2xl bg-white p-4 dark:bg-slate-900/60 sm:min-w-0">
      <div className="flex items-start gap-3">
        <div
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-black text-white ${RANK_TONE[idx % RANK_TONE.length]}`}
        >
          {s.rank_no}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-extrabold text-slate-900 dark:text-slate-100">
            {s.thema_nm}
          </p>
          <p className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {s.stk_num}종목 · {s.rising_stk_num}↑ {s.fall_stk_num}↓
          </p>
        </div>
        <div className={`text-right ${tone}`}>
          <p className="text-base font-extrabold tabular-nums">
            {isUp ? "+" : ""}
            {s.flu_rt.toFixed(2)}%
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {s.stocks.slice(0, 4).map((stk) => {
          const stkUp = parseFloat(stk.flu_rt) > 0;
          const stkDown = parseFloat(stk.flu_rt) < 0;
          return (
            <span
              key={stk.stk_cd}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium dark:bg-slate-800"
            >
              <span className="text-slate-700 dark:text-slate-300">
                {stk.stk_nm}
              </span>
              <span
                className={
                  stkUp
                    ? "text-rose-500"
                    : stkDown
                      ? "text-blue-500"
                      : "text-slate-400"
                }
              >
                {stkUp ? "+" : ""}
                {parseFloat(stk.flu_rt).toFixed(1)}%
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
