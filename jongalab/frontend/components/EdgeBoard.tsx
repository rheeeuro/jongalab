"use client";

import { useState } from "react";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeSummaryStrip } from "@/components/EdgeSummaryStrip";
import { EdgeRuleCard } from "@/components/EdgeRuleCard";
import { EdgeRuleDetail } from "@/components/EdgeRuleDetail";

// 이 화면은 읽기 전용 — 실전 투입/종료 등 관리는 /admin/edge-rules(관리자 인증)에서만 한다.
const GROUPS: { status: "live" | "candidate" | "retired"; label: string; desc: string }[] = [
  { status: "live", label: "실전 적용 중", desc: "실제 매매에 반영되는 전략" },
  { status: "candidate", label: "검증 중", desc: "모의 채점만 — 실제 돈은 쓰지 않음" },
  { status: "retired", label: "종료", desc: "" },
];

export function EdgeBoard({ rules }: { rules: EdgeRuleWithDaily[] }) {
  const [selected, setSelected] = useState<EdgeRuleWithDaily | null>(null);

  if (rules.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
        <p className="text-sm text-slate-500 dark:text-slate-400">등록된 전략이 없습니다.</p>
        <p className="mt-1 text-xs text-slate-400">
          전략이 등록되면 매 거래일 아침 자동으로 검증 성적이 쌓입니다.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <EdgeSummaryStrip rules={rules} />

      {GROUPS.map(({ status, label, desc }) => {
        const group = rules.filter((r) => r.status === status);
        if (group.length === 0) return null;
        const cards = (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.map((r) => (
              <EdgeRuleCard key={r.id} rule={r} onOpen={setSelected} />
            ))}
          </div>
        );
        // 종료된 전략은 기본 접힘
        if (status === "retired") {
          return (
            <details key={status} className="group">
              <summary className="mb-3 flex cursor-pointer list-none items-center gap-2 text-sm font-bold text-slate-400">
                <span>{label}</span>
                <span className="rounded-full bg-slate-100 px-1.5 text-xs dark:bg-slate-800">{group.length}</span>
              </summary>
              {cards}
            </details>
          );
        }
        return (
          <section key={status}>
            <h2 className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-200">
                {label}
                <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-500 dark:bg-slate-800">
                  {group.length}
                </span>
              </span>
              {desc && <span className="text-xs text-slate-400 dark:text-slate-500">{desc}</span>}
            </h2>
            {cards}
          </section>
        );
      })}

      <EdgeRuleDetail rule={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
