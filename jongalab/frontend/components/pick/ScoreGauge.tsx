import { ScoreBreakdown, StockReport } from "@/types";
import { PANEL } from "@/lib/ui";
import { scoreAxes, scoreSentence } from "@/lib/report";

/** 종합 점수 — **게이지 한 개**에 3축(수급·기술·재료)을 색 구간으로 낸다.
 *
 * 축은 옆 '왜 뽑혔나' 카드와 같은 3축이고 색도 같은 소스(`lib/report.SCORE_AXES`)를 써서,
 * 색이 두 카드를 잇는 열쇠가 된다. 항목별 막대를 줄줄이 세우지 않는다 — 회색 트랙이 반복되면
 * 세로만 길고 "이 점수가 무엇으로 채워졌나"는 오히려 안 읽힌다.
 * 구성 점수는 **서버가 준 값만** 쓴다(`score_breakdown`) — 가중치는 주간 튜닝으로 바뀌므로
 * 화면이 미러를 들면 조용히 어긋난다. 경위: docs/history/frontend-ui.md
 */
export function ScoreGauge({
  report: r,
  breakdown,
}: {
  report: StockReport;
  breakdown?: ScoreBreakdown | null;
}) {
  const axes = breakdown ? scoreAxes(breakdown) : [];
  const penalty = breakdown?.penalty ?? null;
  // 가중치가 바뀐 뒤 조회한 과거 리포트는 재계산 총점이 저장된 점수와 다를 수 있다 — 감춰선 안 된다.
  const drifted =
    breakdown != null && Math.abs(breakdown.total - r.score) >= 1;

  return (
    <section className={`${PANEL} flex flex-col`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
          종합 점수
        </h2>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          100점 기준
        </span>
      </div>

      <p className="mt-2 text-4xl font-black text-slate-900 dark:text-slate-100">
        {r.score.toFixed(0)}
        <span className="ml-1 text-base font-bold text-slate-400">점</span>
      </p>

      {axes.length > 0 ? (
        <>
          {/* 게이지 — 트랙(회색)이 남은 점수, 색 구간이 축별 획득 점수. 구간 사이 2px 틈으로 경계를 형태로도 낸다. */}
          <div className="mt-3 flex h-3.5 w-full gap-0.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            {axes
              .filter((a) => a.points > 0)
              .map((a) => (
                <div
                  key={a.key}
                  className={a.bar}
                  style={{ width: `${a.points}%` }}
                  title={`${a.label} ${a.points.toFixed(1)}점 / ${a.maxPoints.toFixed(0)}점`}
                />
              ))}
          </div>

          {/* ⚠️ 남는 공간을 범례 줄 사이로 분산하지 말 것 — 짝 카드가 길면 줄 간격이 42~166px 까지
              벌어져 세 줄이 따로 떠 보인다. 간격은 8px 고정이고, 카드 높이는 각 줄의
              '못 받음' 줄이 채운다. */}
          <ul className="mt-3 space-y-2">
            {axes.map((a) => (
              <li key={a.key} className="flex items-baseline gap-2">
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${a.bar}`}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-extrabold text-slate-700 dark:text-slate-200">
                      {a.label}
                    </span>
                    <span className="text-sm font-bold tabular-nums text-slate-500 dark:text-slate-400">
                      <span className={a.text}>{a.points.toFixed(0)}</span>
                      <span className="text-slate-300 dark:text-slate-600">
                        {" "}
                        / {a.maxPoints.toFixed(0)}
                      </span>
                    </span>
                  </p>
                  <p className="text-[11px] leading-snug font-medium break-keep text-slate-400 dark:text-slate-500">
                    {a.earned.length > 0 ? a.earned.join(" · ") : a.hint}
                  </p>
                  {/* 못 받은 항목 — "이 축이 왜 만점이 아닌가"의 답이다(카드 높이도 이 줄이 채운다). */}
                  {a.missed.length > 0 && (
                    <p className="text-[11px] leading-snug font-medium break-keep text-slate-300 dark:text-slate-600">
                      못 받음 · {a.missed.join(" · ")}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>

          {penalty && (
            <p className="mt-2.5 text-[11px] font-bold break-keep text-slate-500 dark:text-slate-400">
              {penalty.label} {penalty.points.toFixed(0)}점
              <span className="ml-1 font-medium text-slate-400 dark:text-slate-500">
                — 하루에 너무 많이 오른 종목은 점수를 깎아요
              </span>
            </p>
          )}

          <p className="mt-3 text-xs leading-relaxed break-keep text-slate-500 dark:text-slate-400">
            {scoreSentence(r, axes)}
          </p>

          {drifted && (
            <p className="mt-1.5 text-[11px] leading-relaxed font-medium break-keep text-slate-400 dark:text-slate-500">
              구성은 지금 기준으로 다시 계산한 값이라, 이 리포트를 만들 때의 총점
              {" "}{r.score.toFixed(0)}점과 합이 조금 달라요(합 {breakdown!.total.toFixed(0)}점).
            </p>
          )}
        </>
      ) : (
        <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
          점수 구성 값이 없어요.
        </p>
      )}
    </section>
  );
}
