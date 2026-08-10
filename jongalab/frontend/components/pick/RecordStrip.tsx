import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { RecordSummary } from "@/types";

function pctColor(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-600 dark:text-slate-300";
}

function signed(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

/** 최근 N 거래일 누적 성적 — 추천 목록 바로 위에서 "얼마나 믿을 수 있나"에 답한다.
 *
 * 승률·평균 갭은 **선정 종목 전체**(selected=1, 갭 체크 완료)가 모수다. 평균 실체결은
 * 매매 경로에서 채워져 표본이 더 적을 수 있어(`exec_samples`) 모수가 다르면 그 사실을
 * 화면에 적는다 — 두 수치를 같은 모수로 읽으면 성적이 부풀려진다.
 */
export function RecordStrip({
  summary,
  href = "/record",
}: {
  summary: RecordSummary | null;
  href?: string;
}) {
  if (!summary || summary.picks === 0) return null;

  // 실체결 라벨 구간이 갭 구간과 다르면 그 사실을 부제에 적는다 —
  // 같은 창의 값처럼 나란히 놓으면 성적이 부풀려 읽힌다.
  const execWindowDiffers =
    summary.avg_exec_ret !== null && summary.exec_days !== summary.days;

  return (
    <Link
      href={href}
      className="group block rounded-2xl bg-white p-4 transition-all hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-900/60"
    >
      <div className="flex items-center gap-1.5">
        <p className="text-[11px] font-extrabold tracking-wide text-slate-400 uppercase dark:text-slate-500">
          최근 {summary.days}거래일 성적
        </p>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          · {summary.picks}종목
        </span>
        <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600" />
      </div>

      <div className="mt-2.5 grid grid-cols-3 gap-2">
        <Metric
          label="승률"
          value={`${summary.win_rate.toFixed(0)}%`}
          sub={`${summary.wins}승 ${summary.losses}패`}
          tone="text-slate-900 dark:text-slate-100"
        />
        <Metric
          label="평균 갭"
          value={signed(summary.avg_gap_pct)}
          sub="종가→익일 시가"
          tone={pctColor(summary.avg_gap_pct)}
        />
        <Metric
          label="평균 실체결"
          value={
            summary.avg_exec_ret === null ? "—" : signed(summary.avg_exec_ret)
          }
          sub={
            summary.avg_exec_ret === null
              ? "집계 전"
              : execWindowDiffers
                ? `최근 ${summary.exec_days}거래일만`
                : "체결가 기준"
          }
          tone={
            summary.avg_exec_ret === null
              ? "text-slate-400"
              : pctColor(summary.avg_exec_ret)
          }
        />
      </div>
    </Link>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: string;
}) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[10px] font-bold text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p
        className={`mt-0.5 truncate text-lg font-black tabular-nums ${tone} sm:text-xl`}
      >
        {value}
      </p>
      <p className="truncate text-[10px] font-medium text-slate-400 dark:text-slate-500">
        {sub}
      </p>
    </div>
  );
}
