import { RecordSummary } from "@/types";
import { formatReportDate } from "@/components/pick/DateStepper";
import Link from "next/link";

function pctColor(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-600 dark:text-slate-300";
}

function signed(pct: number, digits = 2): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

/** 누적 성적 패널 — `/record` 상단. 홈의 `RecordStrip` 을 펼친 버전이다.
 *
 * 승률·평균 갭의 모수는 **선정 종목 전체**(selected=1, 갭 체크 완료)이고, 평균 실체결은
 * 매매 경로에서 채워져 표본이 더 적을 수 있다(`exec_samples`). 좋은 수치만 크게 띄우지
 * 않기 위해 최고일과 **최악일을 같은 크기로** 나란히 낸다.
 */
export function RecordSummaryPanel({
  summary,
}: {
  summary: RecordSummary | null;
}) {
  if (!summary || summary.picks === 0) {
    return (
      <section className="rounded-3xl bg-white p-6 text-center dark:bg-slate-900/60">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          아직 집계할 성적이 없습니다.
        </p>
      </section>
    );
  }

  // 실체결 라벨은 매매 경로 가동 이후 구간에만 있다 — 갭과 창이 다르면 그 구간을 적는다.
  const execWindowDiffers =
    summary.avg_exec_ret !== null && summary.exec_days !== summary.days;
  const execSub =
    summary.avg_exec_ret === null
      ? "집계 전"
      : execWindowDiffers
        ? `${summary.exec_from_date} ~ ${summary.exec_to_date} · ${summary.exec_days}거래일 구간만`
        : "체결가 기준(수수료·세금 전)";

  return (
    <section className="rounded-3xl bg-white p-5 sm:p-6 dark:bg-slate-900/60">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="text-base font-extrabold text-slate-900 sm:text-lg dark:text-slate-100">
          최근 {summary.days}거래일 누적
        </h2>
        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 tabular-nums">
          {summary.from_date} ~ {summary.to_date} · {summary.picks}종목
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric
          label="승률"
          value={`${summary.win_rate.toFixed(1)}%`}
          sub={`${summary.wins}승 ${summary.losses}패${summary.flats ? ` ${summary.flats}보합` : ""}`}
        />
        <Metric
          label="평균 갭 수익률"
          value={signed(summary.avg_gap_pct)}
          sub="종가 매수 → 익일 시가"
          tone={pctColor(summary.avg_gap_pct)}
        />
        <Metric
          label="평균 실체결 수익률"
          value={
            summary.avg_exec_ret === null ? "—" : signed(summary.avg_exec_ret)
          }
          sub={execSub}
          tone={
            summary.avg_exec_ret === null
              ? "text-slate-400"
              : pctColor(summary.avg_exec_ret)
          }
        />
        <div className="min-w-0 space-y-2">
          <DayRow label="최고" day={summary.best_day} />
          <DayRow label="최악" day={summary.worst_day} />
        </div>
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
        선정 종목 <b>전체</b>를 종가에 사서 다음 거래일 시가에 판다고 가정한 과거 기록입니다.
        일부만 골라 담은 성적이 아니며, 미래 수익을 보장하지 않습니다.
      </p>
    </section>
  );
}

function Metric({
  label,
  value,
  sub,
  tone = "text-slate-900 dark:text-slate-100",
}: {
  label: string;
  value: string;
  sub: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[11px] font-bold text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p className={`mt-0.5 text-2xl font-black tabular-nums ${tone}`}>
        {value}
      </p>
      <p className="mt-0.5 text-[11px] leading-snug font-medium text-slate-400 dark:text-slate-500">
        {sub}
      </p>
    </div>
  );
}

function DayRow({
  label,
  day,
}: {
  label: string;
  day: RecordSummary["best_day"];
}) {
  if (!day) return null;
  return (
    <Link
      href={`/reports/${day.date}`}
      className="flex items-baseline gap-1.5 rounded-lg text-xs font-bold hover:underline"
    >
      <span className="shrink-0 text-slate-400 dark:text-slate-500">
        {label}
      </span>
      <span className="min-w-0 truncate text-slate-700 dark:text-slate-200">
        {formatReportDate(day.date)}
      </span>
      <span className={`ml-auto shrink-0 tabular-nums ${pctColor(day.pct)}`}>
        {signed(day.pct)}
      </span>
    </Link>
  );
}
