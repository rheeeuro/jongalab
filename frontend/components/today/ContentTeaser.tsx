import Link from "next/link";
import { ContentAnalysis } from "@/types";
import { ContentCard } from "@/components/ContentCard";
import { ArrowRight } from "lucide-react";

interface Props {
  items: ContentAnalysis[];
  market: string;
}

export function ContentTeaser({ items, market }: Props) {
  if (!items.length) return null;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-2xl">
          오늘 주목할 콘텐츠
        </h2>
        <Link
          href={`/feed?market=${market}&page=1`}
          className="inline-flex items-center gap-1 text-xs font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          전체 보기
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        {items.map((item) => (
          <ContentCard key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
