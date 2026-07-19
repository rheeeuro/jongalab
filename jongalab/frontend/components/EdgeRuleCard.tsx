"use client";

import Link from "next/link";
import type { EdgeRuleWithDaily } from "@/types";
import { Sparkline } from "@/components/Sparkline";
import {
  familyMeta,
  roleMeta,
  fmtPct,
  retTone,
  TONE_TEXT,
  STATUS_LABEL,
  STATUS_BADGE,
  STAT_META,
  isPromotionCandidate,
} from "@/lib/edge";

export function EdgeRuleCard({
  rule,
}: {
  rule: EdgeRuleWithDaily;
}) {
  const s = rule.stats;
  const fam = familyMeta(rule.family);
  const role = roleMeta(rule.role);
  const isLive = rule.status === "live";
  const isRetired = rule.status === "retired";
  const promo = isPromotionCandidate(rule);

  // 스파크라인: 일별 평균 수익 시계열(결측 제외). 2점 미만이면 미표시.
  const series = rule.daily.map((d) => d.mean_net_ret).filter((v): v is number => v !== null);
  const meanTone = retTone(s?.mean_net);

  // 검증 진행바: 검증 횟수 n / 필요 횟수 min_sample (stats 미생성이면 0회로 취급)
  const n = s?.n ?? 0;
  const hasData = n > 0;
  const progress = Math.min(100, Math.round((n / rule.min_sample) * 100));

  return (
    <Link
      href={"/lab/" + encodeURIComponent(rule.name)}
      className={`group flex w-full flex-col gap-2 rounded-2xl border p-4 text-left transition-colors ${
        isLive
          ? "border-emerald-200 bg-emerald-50/40 hover:bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/5 dark:hover:bg-emerald-500/10"
          : isRetired
            ? "border-slate-100 bg-white opacity-60 hover:opacity-100 dark:border-slate-800 dark:bg-[#1c1c22]"
            : "border-slate-100 bg-white hover:border-slate-200 dark:border-slate-800 dark:bg-[#1c1c22] dark:hover:border-slate-700"
      }`}
    >
      {/* 헤더: 전략 유형 + 상태 */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
            {rule.title ?? rule.name}
          </p>
          <span className="mt-0.5 inline-flex flex-wrap items-center gap-1 text-[10px] font-semibold text-slate-400 dark:text-slate-500">
            {fam.label}
            <span className={`rounded-full px-1.5 py-px font-bold ${role.badge}`} title={role.hint}>
              {role.label}
            </span>
          </span>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[rule.status]}`}>
            {STATUS_LABEL[rule.status]}
          </span>
          {promo && (
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-600 dark:bg-rose-500/15 dark:text-rose-300">
              검증 통과
            </span>
          )}
        </div>
      </div>

      {/* 설명 — 상태와 무관하게 2줄 높이를 고정해 카드 크기를 맞춘다 */}
      <p className="line-clamp-2 min-h-[2.4375rem] text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {rule.description}
      </p>

      {/* 성적 슬롯 (거래비용 차감 기준) — 데이터가 없어도 같은 높이의 한 줄을 채운다.
          mt-auto: 그리드에서 카드가 늘어나면 아래 슬롯들을 바닥에 정렬 */}
      {hasData && s ? (
        <div className="mt-auto flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
          <span className="text-slate-500 dark:text-slate-400">
            {STAT_META.n.label}{" "}
            <span className="font-bold tabular-nums text-slate-700 dark:text-slate-200">{s.n}</span>
          </span>
          <span className="text-slate-500 dark:text-slate-400">
            {STAT_META.mean_net.label}{" "}
            <span className={`font-bold tabular-nums ${TONE_TEXT[meanTone]}`}>{fmtPct(s.mean_net)}</span>
          </span>
          <span className="text-slate-500 dark:text-slate-400">
            {STAT_META.win_rate.label}{" "}
            <span className="font-bold tabular-nums text-slate-700 dark:text-slate-200">
              {s.win_rate !== null ? `${Math.round(s.win_rate * 100)}%` : "—"}
            </span>
          </span>
        </div>
      ) : (
        <p className="mt-auto truncate text-xs text-slate-400 dark:text-slate-500">
          아직 검증 기록 없음 ({rule.registered_at} 등록, 매 거래일 자동 채점)
        </p>
      )}

      {/* 하단 슬롯: 보수적 수익 + 스파크라인 — 항상 렌더해 높이 고정 */}
      <div className="mt-0.5 flex h-6 items-center justify-between gap-3">
        <span className="shrink-0 text-[11px] text-slate-400 dark:text-slate-500">
          {STAT_META.ci_low.label}{" "}
          {hasData && s ? (
            <span className={`font-semibold tabular-nums ${TONE_TEXT[retTone(s.ci_low)]}`}>{fmtPct(s.ci_low)}</span>
          ) : (
            <span className="font-semibold tabular-nums">—</span>
          )}
        </span>
        {hasData && series.length >= 2 && (
          <div className="relative h-6 w-24 shrink-0">
            <Sparkline data={series} tone={meanTone} className="h-full w-full" />
          </div>
        )}
      </div>

      {/* 검증 진행바 — 검증 중 카드는 기록이 없어도(0회) 항상 표시 */}
      {rule.status === "candidate" && (
        <div className="mt-0.5">
          <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500">
            <span>검증 진행</span>
            <span className="tabular-nums">{n}/{rule.min_sample}회</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className={`h-full rounded-full ${promo ? "bg-rose-500" : "bg-slate-300 dark:bg-slate-600"}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
    </Link>
  );
}
