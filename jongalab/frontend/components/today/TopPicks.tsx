import Link from "next/link";
import { StockReport } from "@/types";
import { ArrowUpRight, TrendingUp, FileText, Trophy } from "lucide-react";
import { StockPriceBadge } from "@/components/StockPriceBadge";

interface Props {
  pick: StockReport | null;
}

export function TopPicks({ pick }: Props) {
  if (!pick) {
    return (
      <section>
        <SectionHeader title="오늘의 추천" />
        <div className="rounded-3xl bg-white p-6 text-center text-sm text-slate-400 dark:bg-slate-900/60">
          오늘은 아직 리포트가 준비되지 않았어요.
        </div>
      </section>
    );
  }

  const Card = (
    <div className="group relative overflow-hidden rounded-3xl bg-gradient-to-br from-rose-50 to-orange-50 p-5 transition-all hover:shadow-md dark:from-rose-950/40 dark:to-orange-950/30 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold text-rose-600 dark:bg-slate-900/50 dark:text-rose-400">
          <TrendingUp className="h-3.5 w-3.5" />
          강력 매수
        </span>
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-extrabold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          <Trophy className="h-3.5 w-3.5" />
          종목 랭킹 1위
        </span>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white/70 px-2.5 py-1 text-xs font-extrabold text-slate-700 tabular-nums dark:bg-slate-900/50 dark:text-slate-200">
          종합 {Math.round(pick.score)}점
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-baseline gap-2">
        <p className="truncate text-2xl font-black tracking-tight text-slate-900 dark:text-slate-100 sm:text-3xl">
          {pick.stock_name || "종목 없음"}
        </p>
        {pick.stock_code && <StockPriceBadge ticker={pick.stock_code} />}
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {pick.reason}
      </p>

      {pick.stock_code && (
        <div className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-slate-700 dark:text-slate-200">
          자세히 보기
          <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </div>
      )}
    </div>
  );

  return (
    <section>
      <SectionHeader
        title="오늘의 추천"
        action={
          <Link
            href={`/reports/${pick.report_date}`}
            className="inline-flex items-center gap-1 rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-bold text-white transition-opacity hover:opacity-90 dark:bg-white dark:text-slate-900"
          >
            <FileText className="h-3.5 w-3.5" />
            리포트 보기
          </Link>
        }
      />

      {pick.stock_code ? (
        <Link href={`/stocks/${pick.stock_code}`}>{Card}</Link>
      ) : (
        Card
      )}
    </section>
  );
}

function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-2">
      <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
        {title}
      </h2>
      {action}
    </div>
  );
}
