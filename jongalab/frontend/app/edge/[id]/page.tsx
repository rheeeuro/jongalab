import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { getEdgeRuleWithDaily } from "@/lib/api";
import { EdgeRuleDetailContent } from "@/components/EdgeRuleDetailContent";

type Props = {
  params: Promise<{ id: string }>;
};

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const numericId = Number(id);
  const rule = Number.isInteger(numericId) && numericId > 0 ? await getEdgeRuleWithDaily(numericId, 60) : null;
  return {
    title: rule ? `${rule.title ?? rule.name} · 전략 실험실` : "전략 상세",
    alternates: { canonical: `/edge/${id}` },
  };
}

export default async function EdgeRulePage({ params }: Props) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isInteger(numericId) || numericId <= 0) notFound();

  const rule = await getEdgeRuleWithDaily(numericId, 60);
  if (!rule) notFound();

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-5 sm:px-6 sm:py-8">
        <Link
          href="/edge"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowLeft className="h-4 w-4" />
          실험실
        </Link>

        <section className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm sm:p-6 dark:border-slate-800 dark:bg-[#17171C]">
          <EdgeRuleDetailContent rule={rule} />
        </section>
      </div>
    </main>
  );
}
