import Link from "next/link";
import { MentionStats } from "@/types";
import { MentionTreemapCard } from "@/components/MentionTreemapCard";
import { ArrowRight } from "lucide-react";

export function MentionPulse({ stats }: { stats: MentionStats | null }) {
  if (!stats || !stats.sectors?.length) return null;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          지금 뜨는 기업
        </h2>
        <Link
          href="/feed"
          className="inline-flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          콘텐츠 전체
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <MentionTreemapCard stats={stats} />
    </section>
  );
}
