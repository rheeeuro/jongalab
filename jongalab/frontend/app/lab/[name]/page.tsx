import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { getEdgeRuleWithDailyByName, getEdgeRuleMatched } from "@/lib/api";
import { EdgeRuleDetailContent } from "@/components/EdgeRuleDetailContent";

type Props = {
  params: Promise<{ name: string }>;
};

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { name } = await params;
  const rule = await getEdgeRuleWithDailyByName(name, 60);
  return {
    title: rule ? `${rule.title ?? rule.name} · 전략 실험실` : "전략 상세",
    alternates: { canonical: rule ? `/lab/${encodeURIComponent(rule.name)}` : `/lab/${encodeURIComponent(name)}` },
  };
}

export default async function EdgeRulePage({ params }: Props) {
  const { name } = await params;
  const rule = await getEdgeRuleWithDailyByName(name, 60);
  if (!rule) notFound();
  const matchedHistory = await getEdgeRuleMatched(rule.id, 30);

  return (
    <main className="min-h-screen bg-slate-100/70 dark:bg-[#101014]">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
        <Link
          href="/lab"
          className="inline-flex items-center gap-1 text-sm font-bold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          실험실
        </Link>

        <EdgeRuleDetailContent rule={rule} matchedHistory={matchedHistory} />
      </div>
    </main>
  );
}
