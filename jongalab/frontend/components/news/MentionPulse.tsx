import { MentionStats } from "@/types";
import { MentionTreemapCard } from "@/components/MentionTreemapCard";

/** 콘텐츠에서 언급이 몰린 기업 트리맵 — 뉴스 탭의 '콘텐츠' 뷰 상단.
 * 아래 콘텐츠 목록과 같은 화면이라 '전체 보기' 링크는 두지 않는다. */
export function MentionPulse({ stats }: { stats: MentionStats | null }) {
  if (!stats || !stats.sectors?.length) return null;

  return (
    <section>
      <h2 className="mb-3 text-lg font-extrabold tracking-tight text-slate-900 sm:text-xl dark:text-slate-100">
        지금 뜨는 기업
      </h2>
      <MentionTreemapCard stats={stats} />
    </section>
  );
}
