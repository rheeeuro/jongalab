import type { EdgeRule } from "@/types";
import { isPromotionCandidate, isMeasurementOnly, isDecided, ROLE_META } from "@/lib/edge";

// 요약 스탯 타일(가로 스크롤). 모바일에서 한 줄에 다 안 들어가도 스크롤로 본다.
export function EdgeSummaryStrip({ rules }: { rules: EdgeRule[] }) {
  // 적용 중/검증 중은 실제 선정에 쓰이는 전략만 센다 — 측정용(기준선)은 파이프라인 밖이라
  // 별도 타일로 뺀다(기준선이 '적용 중'에 섞이면 매매에 반영되는 전략 수가 부풀려 보인다).
  const pipeline = rules.filter((r) => !isMeasurementOnly(r));
  const live = pipeline.filter((r) => r.status === "live").length;
  // 판정이 끝난 candidate 는 '검증 중'도 '검증 통과'도 아니다 — 더 심사하지 않으므로 따로 센다
  // (종결된 rule 이 게이트를 통과한 상태로 남아 '검증 통과' 숫자를 부풀리는 것을 막는다).
  const decided = pipeline.filter(isDecided).length;
  const candidate = pipeline.filter((r) => r.status === "candidate" && !isDecided(r)).length;
  const retired = pipeline.filter((r) => r.status === "retired").length;
  const promo = rules.filter((r) => isPromotionCandidate(r) && !isDecided(r)).length;
  const measured = rules.filter((r) => isMeasurementOnly(r) && r.status !== "retired").length;

  const tiles: { label: string; value: number; accent: string }[] = [
    { label: "적용 중", value: live, accent: "text-emerald-600 dark:text-emerald-400" },
    { label: "검증 중", value: candidate, accent: "text-slate-700 dark:text-slate-200" },
    { label: "검증 통과", value: promo, accent: "text-rose-600 dark:text-rose-400" },
    { label: ROLE_META.benchmark.label, value: measured, accent: "text-sky-600 dark:text-sky-400" },
    { label: "판정 종결", value: decided, accent: "text-slate-400 dark:text-slate-500" },
    { label: "종료", value: retired, accent: "text-slate-400 dark:text-slate-500" },
  ];

  return (
    <div className="-mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="flex min-w-[92px] shrink-0 flex-col rounded-2xl border border-slate-100 bg-white px-4 py-3 dark:border-slate-800 dark:bg-[#1c1c22]"
        >
          <span className="text-[11px] font-semibold text-slate-400 dark:text-slate-500">
            {t.label}
          </span>
          <span className={`mt-0.5 text-2xl font-extrabold tabular-nums ${t.accent}`}>
            {t.value}
          </span>
        </div>
      ))}
    </div>
  );
}
