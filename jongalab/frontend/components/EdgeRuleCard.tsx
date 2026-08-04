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
  PROMO_MIN_DAYS,
  promoBlockers,
  isPromotionCandidate,
  isMeasurementOnly,
  isDecided,
  decisionLabel,
  verifyProgress,
} from "@/lib/edge";

export function EdgeRuleCard({
  rule,
}: {
  rule: EdgeRuleWithDaily;
}) {
  const s = rule.stats;
  const fam = familyMeta(rule.family);
  const role = roleMeta(rule.role);
  // 측정용(기준선)은 선정에 반영되지 않으므로 '적용 중' 강조색·상태·검증 진행도를 쓰지 않는다.
  const measure = isMeasurementOnly(rule);
  const isLive = rule.status === "live" && !measure;
  const isRetired = rule.status === "retired";
  const promo = isPromotionCandidate(rule);
  // 판정이 끝난 candidate — '심사 중'이 아니라 결과(판정 탈락·재현 실패)를 찍는다.
  const decided = isDecided(rule);
  const verdict = decisionLabel(rule);

  // 스파크라인: 일별 평균 수익 시계열(결측 제외). 2점 미만이면 미표시.
  const series = rule.daily.map((d) => d.mean_net_ret).filter((v): v is number => v !== null);
  const meanTone = retTone(s?.mean_net);
  const blockers = promoBlockers(rule);

  // 검증 진행바: 표본 축적(거래일) 진행도 — lib/edge.verifyProgress 단일 소스(목록 정렬과 동일).
  // 게이트를 막는 조건은 서버가 stats.promo_blockers 로 내려준다(프론트 재계산 금지).
  const { n, nDays, progress } = verifyProgress(rule);
  const hasData = n > 0;

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
          {/* 측정용은 검증/투입 대상이 아니라 상태를 숨긴다(단, '종료'는 수명 정보라 유지).
              판정 종결도 상태 배지를 숨긴다 — status 는 candidate 그대로라 '검증 중' 배지가
              바로 옆 '판정 탈락' 배지와 정면으로 모순되고, 배지 수가 달라 카드 키도 어긋난다. */}
          {(!measure || isRetired) && !decided && (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[rule.status]}`}>
              {STATUS_LABEL[rule.status]}
            </span>
          )}
          {promo && !decided && (
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-600 dark:bg-rose-500/15 dark:text-rose-300">
              검증 통과
            </span>
          )}
          {decided && verdict && (
            <span
              className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
              title={rule.decision?.confirm?.reasons?.[0] ?? rule.decision?.discovery?.reasons?.[0] ?? undefined}
            >
              {verdict.text}
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

      {/* 하단 슬롯: 보수적 수익(게이트가 보는 값) + 스파크라인 — 항상 렌더해 높이 고정 */}
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

      {/* 검증 상태 — 표본 진행바(거래일)와 **막고 있는 항목**을 분리해 보여준다.
          예전엔 진행바가 min_sample(회수)까지 포함해, 그 조건이 게이트에서 빠진 뒤
          '바는 꽉 찼는데 검증 중'이 되는 모순이 있었다. 이제 바는 심사 대상이 되는 시점만
          나타내고, 통과를 막는 이유는 서버가 준 blockers 를 그대로 적는다.
          **3줄 구조(상태·진행바·설명)를 항상 같은 높이로 렌더한다** — 설명줄을 조건부로 넣었더니
          '남은 조건'이 있는 카드만 키가 커져 그리드가 들쭉날쭉했다(2026-08-04 사용자 지적).
          판정 종결도 같은 3줄을 쓰고 텍스트·색만 바꾼다(더 심사하지 않으므로 바는 회색 고정). */}
      {rule.status === "candidate" && !measure && (
        <div className="mt-0.5">
          <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400 dark:text-slate-500">
            <span className="shrink-0">
              {decided
                ? (verdict?.text ?? "판정 종결")
                : nDays < PROMO_MIN_DAYS
                  ? "표본 쌓는 중"
                  : promo
                    ? "검증 통과"
                    : "심사 중"}
            </span>
            <span className="tabular-nums">
              <span className={!decided && nDays < PROMO_MIN_DAYS ? "text-amber-500 dark:text-amber-400" : ""}>
                {nDays}/{PROMO_MIN_DAYS}일
              </span>
              {n > 0 && <span className="text-slate-300 dark:text-slate-600">{" · "}{n}회</span>}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className={`h-full rounded-full ${
                decided ? "bg-slate-200 dark:bg-slate-700" : promo ? "bg-rose-500" : "bg-slate-300 dark:bg-slate-600"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          {/* 설명줄 — 종결이면 판정 사유, 심사 중이면 막고 있는 항목. 내용이 없어도 같은 높이를
              차지하도록 공백을 넣어 항상 렌더한다(카드 높이 통일). */}
          <p className="mt-1 h-3.5 truncate text-[10px] leading-[0.875rem] text-slate-400 dark:text-slate-500">
            {decided
              ? (rule.decision?.confirm?.reasons?.[0] ??
                 rule.decision?.discovery?.reasons?.[0] ??
                 "검증이 끝나 더 심사하지 않습니다.")
              : !promo && nDays >= PROMO_MIN_DAYS && blockers.length > 0
                ? `남은 조건: ${blockers.join(" · ")}`
                : "\u00A0"}
          </p>
        </div>
      )}
    </Link>
  );
}
