import Link from "next/link";
import { CalendarDays, Info } from "lucide-react";
import { DateStepper, formatReportDate } from "@/components/pick/DateStepper";
import { CARD } from "@/lib/ui";

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
          {/* 기준일은 pill 로 — 본문 텍스트와 같은 모양이면 첫 화면에서 안 읽힌다 */}
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-extrabold text-slate-900 tabular-nums dark:text-slate-100 ${CARD}`}
          >
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />
            {date ? formatReportDate(date) : "리포트 준비 중"}
            <span className="font-bold text-slate-400 dark:text-slate-500">
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

      {/* 제목과 선정 근거를 한 줄에 붙인다 — 모바일 첫 화면에서 지표(MarketPulse)까지
          보이려면 헤더가 세 줄을 넘지 않아야 한다. */}
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h1 className="text-2xl font-black leading-tight tracking-tight text-slate-900 sm:text-3xl dark:text-slate-100">
          오늘의 추천{" "}
          <span className="text-indigo-600 tabular-nums dark:text-indigo-400">
            {pickCount}종목
          </span>
        </h1>
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {ruleCount > 0
            ? `성적을 확인한 전략 ${ruleCount}개가 골랐어요`
            : "수급·차트·뉴스 점수를 합쳐 골랐어요"}
        </p>
      </div>

      {/* 면책 — 닫힌 상태에서도 핵심 문구가 보이게 남긴다(모바일 첫 화면을 문단이 먹지 않게) */}
      <details className="group mt-2 rounded-2xl bg-amber-50/70 px-3 py-2 dark:bg-amber-500/5">
        <summary className="flex cursor-pointer list-none items-start gap-1.5 text-xs leading-relaxed font-semibold text-amber-800 dark:text-amber-300">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            사라는 신호가 아니에요. 투자 결정과 그 결과는 본인 책임이에요.
            <span className="ml-1 font-bold underline underline-offset-2 group-open:hidden">
              자세히
            </span>
          </span>
        </summary>
        <div className="mt-2 space-y-1.5 pl-5 text-xs leading-relaxed text-amber-800/90 dark:text-amber-200/80">
          <p>
            이 목록은 수급(기관·외국인 매수)·차트·뉴스를 보고 자동으로 뽑은 <b>지켜볼 종목</b>이에요.
            사라거나 팔라고 권하는 게 아니고, 실제 매매에도 끼어들지 않아요.
          </p>
          <p>
            성적은 <b>뽑은 종목 전체</b>를 장 마감 가격에 사서 다음 거래일 아침 첫 가격에 팔았다고
            가정한 지난 기록이에요. 앞으로도 그럴 거라는 보장은 없어요.
          </p>
        </div>
      </details>
    </section>
  );
}
