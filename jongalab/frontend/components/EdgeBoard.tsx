"use client";

import { useState } from "react";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeSummaryStrip } from "@/components/EdgeSummaryStrip";
import { EdgeRuleCard } from "@/components/EdgeRuleCard";
import { ROLE_META, verifyProgress, isMeasurementOnly, isDecided, promoPolicy, POLICY_META } from "@/lib/edge";

// 이 화면은 읽기 전용 — 실전 투입/종료 등 관리는 /admin/edge-rules(관리자 인증)에서만 한다.
// 위→아래 순서. **끝난 것(판정 종결·종료)은 이 목록이 아니라 페이지 최하단**에 접힌 채로 둔다
// 더 심사하지 않는 전략이 위쪽 자리를 차지하면 지금 볼 것을 가린다.
const GROUPS: { status: "live" | "candidate"; label: string; desc: string }[] = [
  { status: "live", label: "적용 중", desc: "성적 검사를 통과해서 실제로 쓰고 있는 전략" },
  { status: "candidate", label: "검증 중", desc: "아직 실제로 쓰지 않고 성적만 쌓는 중" },
];

// 역할(role) 탭 — 선정/위험 회피/측정용을 따로 볼 수 있게. 라벨·도움말은 ROLE_META 단일 소스.
const ROLE_TABS: { key: "all" | "selector" | "veto" | "benchmark"; label: string; hint: string }[] = [
  { key: "all", label: "전체", hint: "" },
  { key: "selector", label: ROLE_META.selector.label, hint: ROLE_META.selector.hint },
  { key: "veto", label: ROLE_META.veto.label, hint: ROLE_META.veto.hint },
  { key: "benchmark", label: ROLE_META.benchmark.label, hint: ROLE_META.benchmark.hint },
];

// 끝난 전략용 접힘 섹션 — 검증 횟수 많은 순(진행도 정렬은 '심사 중'에서만 의미가 있다).
function FoldedSection({ label, desc, rules }: { label: string; desc?: string; rules: EdgeRuleWithDaily[] }) {
  if (rules.length === 0) return null;
  return (
    <details className="group">
      <summary className="mb-3 flex cursor-pointer list-none flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm font-bold text-slate-400">
        <span>{label}</span>
        <span className="rounded-full bg-slate-100 px-1.5 text-xs dark:bg-slate-800">{rules.length}</span>
        {desc && <span className="text-xs font-normal text-slate-400 dark:text-slate-500">{desc}</span>}
      </summary>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[...rules]
          .sort((a, b) => (b.stats?.n ?? 0) - (a.stats?.n ?? 0))
          .map((r) => (
            <EdgeRuleCard key={r.id} rule={r} />
          ))}
      </div>
    </details>
  );
}

export function EdgeBoard({ rules }: { rules: EdgeRuleWithDaily[] }) {
  const [roleTab, setRoleTab] = useState<(typeof ROLE_TABS)[number]["key"]>("all");

  if (rules.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 py-16 text-center dark:border-slate-800">
        <p className="text-sm text-slate-500 dark:text-slate-400">등록된 전략이 없어요.</p>
        <p className="mt-1 text-xs text-slate-400">
          전략을 등록하면 거래일마다 아침에 성적이 자동으로 쌓여요.
        </p>
      </div>
    );
  }

  const visible = roleTab === "all" ? rules : rules.filter((r) => r.role === roleTab);
  const activeHint = ROLE_TABS.find((t) => t.key === roleTab)?.hint;

  // 측정용(기준선)은 '적용 중/검증 중' 파이프라인 밖이라 상태 그룹에서 빼고 따로 모은다
  // (검증 통과할 관문이 없는데 '검증 중' 아래 놓이면 검증 대기처럼 읽힌다).
  const measured = visible.filter(isMeasurementOnly);
  // 판정이 끝난 candidate 도 '검증 중'에서 뺀다 — 더 심사하지 않는데 진행도 순 정렬 때문에
  // 그러지 않으면 게이지가 꽉 찬 채 목록 맨 위에 올라와 승격 임박처럼 읽힌다.
  // 파이프라인·측정용 아래, **페이지 최하단**으로 모은다.
  const decided = visible.filter(isDecided);
  const retired = visible.filter((r) => r.status === "retired" && !isMeasurementOnly(r) && !isDecided(r));
  const pipeline = visible.filter(
    (r) => !isMeasurementOnly(r) && !isDecided(r) && r.status !== "retired",
  );

  // 적용 중인 심사 정책 — experimental 은 통계 유의성·확인창을 면제한 실험 모드라 반드시 알린다.
  // (이걸 숨기면 신뢰도가 낮은 전략이 '적용 중'인 이유가 화면에 없어 오해를 준다.)
  const policy = rules.map(promoPolicy).find((p): p is 'strict' | 'experimental' => p !== null);

  return (
    <div className="space-y-6">
      <EdgeSummaryStrip rules={rules} />

      {policy === "experimental" && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-500/30 dark:bg-amber-500/5">
          <p className="text-xs font-bold text-amber-700 dark:text-amber-300">
            현재 심사 기준: {POLICY_META.experimental.label}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-amber-700/80 dark:text-amber-300/80">
            {POLICY_META.experimental.help}
          </p>
        </div>
      )}

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
          이 역할을 하는 전략이 없어요.
        </p>
      )}

      {GROUPS.map(({ status, label, desc }) => {
        // 진행도(카드 진행바와 같은 값) 높은 전략부터 — 통과에 가까운 전략이 위로 온다.
        // 동률이면 검증 횟수 많은 쪽 우선(적용 중처럼 모두 100%인 그룹의 안정적 순서용).
        const group = pipeline
          .filter((r) => r.status === status)
          .sort((a, b) => {
            const pa = verifyProgress(a);
            const pb = verifyProgress(b);
            return pb.progress - pa.progress || pb.n - pa.n;
          });
        if (group.length === 0) return null;
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
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {group.map((r) => (
                <EdgeRuleCard key={r.id} rule={r} />
              ))}
            </div>
          </section>
        );
      })}

      {/* 측정용 기준선 — 상태·검증 진행도 없이 성적만 본다(카드에서도 숨김) */}
      {measured.length > 0 && (
        <section>
          <h2 className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-200">
              {ROLE_META.benchmark.label} 기준선
              <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-500 dark:bg-slate-800">
                {measured.length}
              </span>
            </span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{ROLE_META.benchmark.hint}</span>
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[...measured]
              .sort((a, b) => (b.stats?.n ?? 0) - (a.stats?.n ?? 0))
              .map((r) => (
                <EdgeRuleCard key={r.id} rule={r} />
              ))}
          </div>
        </section>
      )}

      {/* 끝난 전략 — 페이지 최하단(측정용 기준선 아래), 기본 접힘 */}
      <FoldedSection label="판정 종결" desc="검증이 끝나 더 심사하지 않는 전략" rules={decided} />
      <FoldedSection label="종료" rules={retired} />
    </div>
  );
}
