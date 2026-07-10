"use client";

import { useState } from "react";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeSummaryStrip } from "@/components/EdgeSummaryStrip";
import { EdgeRuleCard } from "@/components/EdgeRuleCard";
import { ROLE_META } from "@/lib/edge";

// 이 화면은 읽기 전용 — 실전 투입/종료 등 관리는 /admin/edge-rules(관리자 인증)에서만 한다.
const GROUPS: { status: "live" | "candidate" | "retired"; label: string; desc: string }[] = [
  { status: "live", label: "적용 중", desc: "검증을 통과해 종목 선정에 반영되는 전략" },
  { status: "candidate", label: "검증 중", desc: "모의 채점으로 성적을 쌓는 중" },
  { status: "retired", label: "종료", desc: "" },
];

// 역할(role) 탭 — 선정/위험 회피/측정용을 따로 볼 수 있게. 라벨·도움말은 ROLE_META 단일 소스.
const ROLE_TABS: { key: "all" | "selector" | "veto" | "benchmark"; label: string; hint: string }[] = [
  { key: "all", label: "전체", hint: "" },
  { key: "selector", label: ROLE_META.selector.label, hint: ROLE_META.selector.hint },
  { key: "veto", label: ROLE_META.veto.label, hint: ROLE_META.veto.hint },
  { key: "benchmark", label: ROLE_META.benchmark.label, hint: ROLE_META.benchmark.hint },
];

export function EdgeBoard({ rules }: { rules: EdgeRuleWithDaily[] }) {
  const [roleTab, setRoleTab] = useState<(typeof ROLE_TABS)[number]["key"]>("all");

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

  const visible = roleTab === "all" ? rules : rules.filter((r) => r.role === roleTab);
  const activeHint = ROLE_TABS.find((t) => t.key === roleTab)?.hint;

  return (
    <div className="space-y-6">
      <EdgeSummaryStrip rules={rules} />

      {/* 역할 탭 — 모바일에서 넘치면 가로 스크롤 */}
      <div className="space-y-1.5">
        <div className="flex gap-1.5 overflow-x-auto pb-0.5" role="tablist" aria-label="전략 역할별 보기">
          {ROLE_TABS.map((t) => {
            const count = t.key === "all" ? rules.length : rules.filter((r) => r.role === t.key).length;
            const active = roleTab === t.key;
            return (
              <button
                key={t.key}
                role="tab"
                aria-selected={active}
                onClick={() => setRoleTab(t.key)}
                className={`flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-bold transition-colors ${
                  active
                    ? "bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
                }`}
              >
                {t.label}
                <span className={`tabular-nums ${active ? "opacity-70" : "opacity-60"}`}>{count}</span>
              </button>
            );
          })}
        </div>
        {activeHint && <p className="text-xs text-slate-400 dark:text-slate-500">{activeHint}</p>}
      </div>

      {visible.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400 dark:border-slate-800">
          이 역할의 전략이 없습니다.
        </p>
      )}

      {GROUPS.map(({ status, label, desc }) => {
        const group = visible.filter((r) => r.status === status);
        if (group.length === 0) return null;
        const cards = (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.map((r) => (
              <EdgeRuleCard key={r.id} rule={r} />
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
    </div>
  );
}
