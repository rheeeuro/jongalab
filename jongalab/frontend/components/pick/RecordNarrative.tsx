import { RecordSummary } from "@/types";
import { recordNarrative } from "@/lib/record";

/** 누적 성적 서술 — `/record` 요약 패널 바로 아래.
 *
 * 위 패널이 같은 숫자를 타일로 보여주지만, 타일만으로는 "승률이 무엇을 센 것인지"가 화면에
 * 없다. 문장은 그 전제(집계 구간·모수·청산 시점)를 함께 읽히게 하고, 검색엔진이 읽을 본문도
 * 이 문단이 유일하다(근거: docs/plan/seo/search-visibility.md).
 */
export function RecordNarrative({ summary }: { summary: RecordSummary | null }) {
  const paragraphs = recordNarrative(summary);
  if (paragraphs.length === 0) return null;

  return (
    <section className="rounded-3xl bg-white p-5 sm:p-6 dark:bg-slate-900/60">
      <h2 className="text-base font-extrabold text-slate-900 sm:text-lg dark:text-slate-100">
        종가베팅 승률과 수익률
      </h2>
      <div className="mt-2 space-y-2">
        {paragraphs.map((text, i) => (
          <p
            key={i}
            className="text-sm leading-relaxed text-slate-600 dark:text-slate-300"
          >
            {text}
          </p>
        ))}
      </div>
    </section>
  );
}
