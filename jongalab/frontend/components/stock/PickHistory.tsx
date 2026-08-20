import Link from "next/link";
import { Crown, FileBarChart, FlaskConical } from "lucide-react";
import { StockReport } from "@/types";
import { morningResult } from "@/lib/report";
import { CARD, CARD_HOVER, PANEL } from "@/lib/ui";

/** 아침 결과 요약 — 갭이 측정된 회차만 모아 평균·최고·최저를 낸다.
 *  측정 전(당일 선정분)까지 분모에 넣으면 평균이 실제보다 0 쪽으로 눌린다. */
function gapSummary(reports: StockReport[]) {
  const pcts = reports
    .map((r) => morningResult(r)?.pct)
    .filter((v): v is number => typeof v === "number");
  if (pcts.length === 0) return null;
  return {
    n: pcts.length,
    avg: pcts.reduce((a, b) => a + b, 0) / pcts.length,
    best: Math.max(...pcts),
    worst: Math.min(...pcts),
  };
}

function toneClass(v: number): string {
  return v > 0
    ? "text-red-600 dark:text-red-400"
    : v < 0
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-500 dark:text-slate-400";
}

function signed(v: number, digits = 1): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** 종가베팅 선정 이력 — 이 종목이 언제 뽑혔고 **다음날 아침에 어떻게 됐는지**.
 *
 * 종목명 칼럼을 두지 않는다(같은 종목 화면에서 같은 이름이 회차마다 반복된다). 그 자리에
 * 아침 갭 결과를 넣는다 — 이 화면에 들어온 사람이 알고 싶은 건 '뽑혔다'가 아니라 '그래서 어땠나'다.
 * 모바일은 한 회차를 2줄로 쓴다(375px 에서 값 6개를 한 줄에 넣으면 종목·섹터가 눌린다).
 */
export function PickHistory({ reports }: { reports: StockReport[] }) {
  if (reports.length === 0) return null;
  const summary = gapSummary(reports);
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" });

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <FileBarChart className="h-4.5 w-4.5 text-indigo-500" />
          종가베팅 선정 이력
        </h2>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          최근 {reports.length}회
        </span>
      </div>

      {/* 성적 요약은 **헤더 아래 한 줄**이다 — 안쪽 블록(`INSET`)으로 두면 카드가 116px 길어져
          짝(일봉 차트)보다 커진다. 값은 아침 결과가 측정된 회차만 모은 것이다. */}
      {summary && (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs font-medium text-slate-500 dark:text-slate-400">
          <span>아침 결과 {summary.n}회 평균</span>
          <span className={`text-lg font-black tabular-nums ${toneClass(summary.avg)}`}>
            {signed(summary.avg, 2)}
          </span>
          <span className="text-[11px]">
            최고{" "}
            <span className={`font-bold tabular-nums ${toneClass(summary.best)}`}>
              {signed(summary.best, 2)}
            </span>{" "}
            · 최저{" "}
            <span className={`font-bold tabular-nums ${toneClass(summary.worst)}`}>
              {signed(summary.worst, 2)}
            </span>
          </span>
        </p>
      )}

      <ul className="mt-3 space-y-2">
        {reports.map((r) => {
          const morning = morningResult(r);
          return (
            <li key={r.report_date}>
              <Link
                href={`/reports/${r.report_date}/${r.stock_code}`}
                className={`group block ${CARD} ${CARD_HOVER} p-3`}
              >
                {/* 1줄: 날짜 · 당일 등락 · 종합점수 */}
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-extrabold tabular-nums text-slate-700 group-hover:text-indigo-600 dark:text-slate-200 dark:group-hover:text-indigo-400">
                    {r.report_date.slice(2).replace(/-/g, ".")}
                  </span>
                  {r.is_leader && (
                    <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                  )}
                  {r.rule_names && (
                    <span title="실험실 룰이 고른 종목" className="flex shrink-0">
                      <FlaskConical className="h-3.5 w-3.5 text-violet-500" />
                    </span>
                  )}
                  {r.report_date === today && (
                    <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-extrabold text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
                      오늘
                    </span>
                  )}
                  <span className="ml-auto text-xs font-medium text-slate-400 dark:text-slate-500">
                    당일{" "}
                    <span
                      className={`font-extrabold tabular-nums ${toneClass(r.change_pct)}`}
                    >
                      {signed(r.change_pct, 2)}
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums">
                    <span className="text-base font-extrabold text-indigo-600 dark:text-indigo-400">
                      {r.score.toFixed(0)}
                    </span>
                    <span className="text-[11px] font-bold text-slate-400">점</span>
                  </span>
                </div>

                {/* 2줄: 수급 등급 · 점수 순위 · 아침 결과.
                    거래대금은 넣지 않는다 — 375px 에서 줄이 넘치고, 회차별 값은 리포트 상세가 낸다. */}
                <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  <span>수급 {r.supply_grade}등급</span>
                  <span className="text-slate-300 dark:text-slate-600">·</span>
                  <span>점수 {r.rank_no}위</span>
                  <span className="ml-auto">
                    {morning ? (
                      <>
                        다음날 아침{" "}
                        <span
                          className={`font-extrabold tabular-nums ${toneClass(morning.pct)}`}
                        >
                          {signed(morning.pct, 2)}
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">
                        아침 결과 대기
                      </span>
                    )}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="mt-2.5 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        <span className="font-bold">당일</span>은 리포트를 만든 시각(장 마감 무렵)의 등락이라 위
        현재가 등락과 다를 수 있어요. <span className="font-bold">다음날 아침</span>은 그날 종가에
        사서 다음 거래일 첫 가격에 팔았다고 가정한 등락이에요(수수료·세금 제외).
      </p>
    </section>
  );
}
