import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { getEdgeRuleWithDailyByName, getEdgeRuleMatched } from "@/lib/api";
import { STATUS_LABEL, STAT_META, fmtPct, roleMeta } from "@/lib/edge";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeRuleDetailContent } from "@/components/EdgeRuleDetailContent";

type Props = {
  params: Promise<{ name: string }>;
};

export const dynamic = "force-dynamic";

// description 은 룰 설명 + 검증 성적을 그대로 싣는다. 역할(매수/위험 회피/측정용)을 앞에
// 붙이는 건 필수다 — 빼면 제외 규칙의 성적이 매수 전략 수익률처럼 읽힌다.
function ruleDescription(rule: EdgeRuleWithDaily): string {
  const s = rule.stats;
  // 성적을 룰 설명보다 **앞에** 둔다 — 설명이 길어 뒤로 밀면 검색 결과 스니펫에서 잘린다.
  const stat =
    s && s.n > 0
      ? ` · 검증 ${s.n}회${s.n_days != null ? `(${s.n_days}거래일)` : ""}` +
        `${s.win_rate !== null ? ` · ${STAT_META.win_rate.label} ${Math.round(s.win_rate * 100)}%` : ""}` +
        ` · ${STAT_META.mean_net.label} ${fmtPct(s.mean_net)}(거래비용 차감)`
      : "";
  return `종가베팅 ${roleMeta(rule.role).label} 전략 · ${STATUS_LABEL[rule.status] ?? rule.status}${stat}. ${rule.description}`;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { name } = await params;
  const rule = await getEdgeRuleWithDailyByName(name, 60);
  return {
    title: rule
      ? `${rule.title ?? rule.name} - 종가베팅 전략 검증`
      : "전략 상세",
    description: rule ? ruleDescription(rule) : undefined,
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
