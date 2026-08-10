import { StockReport } from "@/types";
import { StockReportCard, finalGapPct } from "@/components/StockReportCard";

function pctColor(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-500";
}

/** 그날 선정 종목의 갭 결과 요약. 갭 체크 전(당일 저녁~익일 아침)이면 null. */
function dayResult(reports: StockReport[]) {
  const pcts = reports
    .map(finalGapPct)
    .filter((p): p is number => p !== null);
  if (pcts.length === 0) return null;
  const wins = pcts.filter((p) => p > 0).length;
  const losses = pcts.filter((p) => p < 0).length;
  const avg = pcts.reduce((s, p) => s + p, 0) / pcts.length;
  return { wins, losses, total: pcts.length, avg };
}

/** 추천 종목 목록 — 이 사이트의 본체.
 *
 * 정렬은 백엔드가 준 순서(점수 내림차순)를 그대로 쓰고 화면에서 다시 매기지 않는다.
 * 검색·정렬 컨트롤은 두지 않는다(하루 10종목 규모라 눈으로 훑는 편이 빠르다).
 */
export function PickList({
  reports,
  date,
  ruleTitleMap,
  action,
}: {
  reports: StockReport[];
  date: string;
  ruleTitleMap: Map<string, string>;
  /** 결과 줄 우측에 붙일 도구 버튼(시드 배분 모달 등). 세로 공간을 먹지 않는 것만 넣는다. */
  action?: React.ReactNode;
}) {
  if (reports.length === 0) {
    return (
      <section className="rounded-3xl bg-white p-10 text-center dark:bg-slate-900/60">
        <p className="text-sm font-bold text-slate-600 dark:text-slate-300">
          이 날짜의 추천 종목이 없습니다.
        </p>
        <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
          장 마감 후 리포트가 만들어집니다. 다른 거래일을 선택해 보세요.
        </p>
      </section>
    );
  }

  const result = dayResult(reports);

  return (
    <section>
      {(result || action) && (
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl bg-white px-4 py-3 text-xs font-bold dark:bg-slate-900/60">
          {result ? (
            <>
              <span className="text-slate-400 dark:text-slate-500">
                이 날 결과
              </span>
              <span className="text-slate-700 tabular-nums dark:text-slate-200">
                {result.wins}승 {result.losses}패
                <span className="ml-1 font-medium text-slate-400">
                  / {result.total}종목
                </span>
              </span>
              <span className="inline-flex items-baseline gap-1">
                <span className="text-slate-400 dark:text-slate-500">평균</span>
                <span className={`tabular-nums ${pctColor(result.avg)}`}>
                  {result.avg > 0 ? "+" : ""}
                  {result.avg.toFixed(2)}%
                </span>
              </span>
            </>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">
              결과는 다음 거래일 아침에 채워집니다
            </span>
          )}
          {action && <div className="ml-auto shrink-0">{action}</div>}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {reports.map((r) => (
          <StockReportCard
            key={r.stock_code}
            report={r}
            date={date}
            ruleTitles={(r.rule_names ?? "")
              .split(",")
              .filter(Boolean)
              .map((n) => ruleTitleMap.get(n) || n)}
          />
        ))}
      </div>
    </section>
  );
}
