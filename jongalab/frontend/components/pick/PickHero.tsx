import Link from "next/link";
import { CalendarDays, Info } from "lucide-react";
import { DateStepper, formatReportDate } from "@/components/pick/DateStepper";

/** 홈 히어로 — 첫 화면에서 "언제 기준 / 무엇을 / 몇 개"를 즉시 답한다.
 *
 * 리포트 기준일을 **최상단**에 둔다: 이 사이트에서 "어느 거래일 추천인가"는 필수 정보이고,
 * 카드 하단으로 밀렸을 때 모바일에서 안 읽혔다.
 *
 * 홈에는 날짜 이동(`DateStepper`)을 두지 않는다 — 홈은 늘 최신 거래일이고, 날짜를 오가는
 * 것은 아카이브(`/reports/{date}`·`/record`)의 역할이다. `dates` 를 넘기면 리포트 화면용
 * 스텝퍼가 붙는다.
 */
export function PickHero({
  date,
  dates,
  pickCount,
  ruleCount,
}: {
  date: string;
  dates?: string[];
  pickCount: number;
  ruleCount: number;
}) {
  return (
    <section>
      {dates ? (
        <DateStepper date={date} dates={dates} />
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-sm font-extrabold text-slate-900 tabular-nums dark:text-slate-100">
            {date ? formatReportDate(date) : "리포트 준비 중"}
            <span className="ml-1 font-bold text-slate-400 dark:text-slate-500">
              종가 기준
            </span>
          </span>
          <Link
            href="/record"
            className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-[11px] font-bold text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <CalendarDays className="h-3.5 w-3.5" />
            지난 추천
          </Link>
        </div>
      )}

      <h1 className="mt-2 text-3xl font-black leading-tight tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
        오늘의 추천{" "}
        <span className="text-indigo-600 tabular-nums dark:text-indigo-400">
          {pickCount}종목
        </span>
      </h1>

      <p className="mt-2 text-sm font-medium text-slate-500 dark:text-slate-400">
        {ruleCount > 0
          ? `실험실에서 검증을 통과한 규칙 ${ruleCount}개가 골랐습니다.`
          : "수급·기술·재료 종합 점수로 골랐습니다."}
      </p>

      {/* 면책 — 닫힌 상태에서도 핵심 문구가 보이게 남긴다(모바일 첫 화면을 문단이 먹지 않게) */}
      <details className="group mt-3 rounded-2xl bg-amber-50/70 px-3.5 py-2.5 dark:bg-amber-500/5">
        <summary className="flex cursor-pointer list-none items-start gap-1.5 text-xs leading-relaxed font-semibold text-amber-800 dark:text-amber-300">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            매수 신호가 아니며 투자 판단의 책임은 본인에게 있습니다.
            <span className="ml-1 font-bold underline underline-offset-2 group-open:hidden">
              자세히
            </span>
          </span>
        </summary>
        <div className="mt-2 space-y-1.5 pl-5 text-xs leading-relaxed text-amber-800/90 dark:text-amber-200/80">
          <p>
            이 목록은 수급·기술·재료 데이터로 자동 선정된 <b>관찰 대상</b>입니다. 특정 종목의
            매수·매도를 권유하지 않으며, 실제 매매에 개입하지 않습니다.
          </p>
          <p>
            성적은 <b>선정 종목 전체</b>를 종가에 사서 다음 거래일 시가에 판다고 가정한
            과거 기록이며, 미래 수익을 보장하지 않습니다.
          </p>
        </div>
      </details>
    </section>
  );
}
