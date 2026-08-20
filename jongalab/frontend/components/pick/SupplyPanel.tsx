import { TrendingUp } from "lucide-react";
import { SupplyHistoryItem } from "@/types";
import { formatBillion } from "@/lib/report";
import { PANEL, INSET } from "@/lib/ui";

/** 수급 등급 칩 색 — 등급 뜻(관심권·수급 약함…)은 '왜 뽑혔나' 축이 내므로 여기선 색만 갖는다. */
const SUPPLY_GRADE_CHIP: Record<string, string> = {
  S: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  A: "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300",
  B: "bg-yellow-100 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300",
  C: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  D: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

function NetBuyCell({ value }: { value: number | null | undefined }) {
  const b = (value ?? 0) / 1e8;
  return (
    <td
      className={`py-2 px-1.5 text-right font-mono text-[11px] font-semibold tabular-nums sm:text-xs ${
        b > 0
          ? "text-red-600 dark:text-red-400"
          : b < 0
            ? "text-blue-600 dark:text-blue-400"
            : "text-slate-400"
      }`}
    >
      {b > 0 ? "+" : ""}
      {b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}
    </td>
  );
}

/** 5일 수급 합계 — 표에 있는 값만 더한다(판정·추정은 하지 않는다). 막대 길이는 최대 절대값 기준. */
function supplyTotals(history: SupplyHistoryItem[]) {
  const sum = (pick: (h: SupplyHistoryItem) => number | null | undefined) =>
    history.reduce((acc, h) => acc + (pick(h) ?? 0), 0);
  const rows = [
    { label: "기관", value: sum((h) => h.inst_net_buy) },
    { label: "외국인", value: sum((h) => h.frgn_net_buy) },
    { label: "개인", value: sum((h) => h.indv_net_buy) },
    { label: "프로그램", value: sum((h) => h.prog_net_buy) },
  ];
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return rows.map((r) => ({
    ...r,
    ratio: Math.round((Math.abs(r.value) / maxAbs) * 100),
  }));
}

/** 수급 — 등급·연속일을 헤더에 두고 본문은 5일 표 하나. 등급 카드를 따로 두지 않는다(값 하나짜리 카드).
 *
 * 리포트 상세(그날 기준)와 종목 상시 페이지(마지막 선정일 기준)가 공유한다. 상시 페이지는 값이
 * 언제 기준인지가 헤더에서 읽혀야 해서 `note` 로 기준일을 덧붙인다.
 */
export function SupplyPanel({
  history,
  grade,
  score,
  days,
  note,
}: {
  history: SupplyHistoryItem[];
  grade: string;
  score: number;
  days: number;
  note?: string;
}) {
  const gradeChip = SUPPLY_GRADE_CHIP[grade] ?? SUPPLY_GRADE_CHIP.D;

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900 dark:text-slate-100">
          <TrendingUp className="h-4.5 w-4.5 text-purple-800 dark:text-purple-300" />
          수급
          {note && (
            <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
              {note}
            </span>
          )}
        </h2>
        <div className="flex items-center gap-1.5">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-extrabold ${gradeChip}`}
          >
            {grade}등급 {score.toFixed(0)}점
          </span>
          <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
            연속 {days}일
          </span>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] text-slate-400 dark:border-slate-700 dark:text-slate-500">
              <th className="py-1.5 px-1.5 text-left font-medium">날짜</th>
              <th className="py-1.5 px-1.5 text-right font-medium">개인</th>
              <th className="py-1.5 px-1.5 text-right font-medium">외국인</th>
              <th className="py-1.5 px-1.5 text-right font-medium">기관</th>
              <th className="py-1.5 px-1.5 text-right font-medium">프로그램</th>
            </tr>
          </thead>
          <tbody>
            {history.length > 0 ? (
              history.map((h: SupplyHistoryItem, i: number) => (
                <tr
                  key={h.date}
                  className={`border-b border-slate-100 dark:border-slate-800 ${
                    i === 0 ? "bg-indigo-50/60 dark:bg-indigo-950/20" : ""
                  }`}
                >
                  <td className="py-2 px-1.5 font-semibold tabular-nums text-slate-600 dark:text-slate-300">
                    {h.date.slice(5).replace("-", ".")}
                    {i === 0 && (
                      <span className="ml-1 text-[10px] font-bold text-indigo-500">
                        기준일
                      </span>
                    )}
                  </td>
                  <NetBuyCell value={h.indv_net_buy} />
                  <NetBuyCell value={h.frgn_net_buy} />
                  <NetBuyCell value={h.inst_net_buy} />
                  <NetBuyCell value={h.prog_net_buy} />
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="py-6 text-center text-slate-400">
                  수급 기록이 없어요
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {/* 5일 합계 — 표의 다섯 줄을 눈으로 더해야 알 수 있던 값이다. 막대는 방향 색(매수 빨강 /
          매도 파랑)이고 길이는 네 주체 중 가장 큰 절대값 기준이다(숫자를 항상 함께 낸다). */}
      {history.length > 0 && (
        <div className={`${INSET} mt-3 px-3 py-2.5`}>
          <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400">
            최근 {history.length}일 합계
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {supplyTotals(history).map(({ label, value, ratio }) => (
              <li key={label} className="flex items-center gap-2">
                <span className="w-12 shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-700/70">
                  <span
                    className={`block h-full rounded-full ${
                      value > 0
                        ? "bg-red-500/80"
                        : value < 0
                          ? "bg-blue-500/80"
                          : "bg-slate-400/60"
                    }`}
                    style={{ width: `${ratio}%` }}
                  />
                </span>
                <span
                  className={`w-16 shrink-0 text-right text-[11px] font-bold tabular-nums ${
                    value > 0
                      ? "text-red-600 dark:text-red-400"
                      : value < 0
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-slate-400"
                  }`}
                >
                  {formatBillion(value, true)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        표의 단위는 억원이고, 그날 사들인 금액이 팔아치운 금액보다 많으면{" "}
        <span className="font-bold text-red-500">빨강(+)</span>, 반대면{" "}
        <span className="font-bold text-blue-500">파랑(−)</span>이에요.
      </p>
    </section>
  );
}
