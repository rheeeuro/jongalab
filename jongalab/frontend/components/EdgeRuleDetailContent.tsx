"use client";

import type { ReactNode } from "react";
import { Activity, BarChart3, CalendarDays, ListChecks, Target } from "lucide-react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { EdgeRuleMatchedDay, EdgeRuleWithDaily } from "@/types";
import {
  familyMeta,
  roleMeta,
  fmtPct,
  retTone,
  TONE_TEXT,
  TONE_FILL,
  STATUS_LABEL,
  STATUS_BADGE,
  STATUS_HELP,
  MEASURE_HELP,
  isMeasurementOnly,
  STAT_META,
  exitLabelText,
  condText,
} from "@/lib/edge";

interface ChartTooltipPayload {
  payload: { date: string; mean: number | null; n: number };
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: ChartTooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-800">
      <p className="font-semibold text-slate-700 dark:text-slate-200">{p.date}</p>
      <p className={TONE_TEXT[retTone(p.mean)]}>평균 수익 {fmtPct(p.mean)}</p>
      <p className="text-slate-400">조건에 걸린 종목 {p.n}개</p>
    </div>
  );
}

const ACCENT: Record<EdgeRuleWithDaily["status"], string> = {
  live: "border-l-emerald-500",
  candidate: "border-l-slate-400",
  retired: "border-l-slate-300 dark:border-l-slate-600",
};

function Panel({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 dark:border-slate-800 dark:bg-[#17171C]">
      <div className="mb-3 flex items-center gap-2 text-sm font-extrabold text-slate-700 dark:text-slate-200">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
          {icon}
        </span>
        {title}
      </div>
      {children}
    </section>
  );
}

export function EdgeRuleDetailContent({
  rule,
  action,
  matchedHistory,
}: {
  rule: EdgeRuleWithDaily;
  action?: ReactNode;
  matchedHistory?: EdgeRuleMatchedDay[];
}) {
  const s = rule.stats;
  const fam = familyMeta(rule.family);
  const role = roleMeta(rule.role);
  // 측정용(기준선)은 검증·실전 투입 대상이 아니라 상태 배지·상태 설명을 다르게 낸다.
  const measure = isMeasurementOnly(rule);
  const chartData = rule.daily.map((d) => ({
    date: d.report_date.slice(5),
    mean: d.mean_net_ret,
    n: d.n_matched,
  }));
  const latestMatched = rule.latest_matched?.matched?.length ? rule.latest_matched : null;

  return (
    <div className="space-y-5">
      <header className={`rounded-2xl border border-slate-200 border-l-4 bg-white p-5 shadow-sm sm:p-6 dark:border-slate-800 dark:bg-[#17171C] ${measure ? "border-l-sky-400" : ACCENT[rule.status]}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {/* 측정용은 검증/투입 대상이 아니라 상태를 숨긴다(단, '종료'는 수명 정보라 유지) */}
              {(!measure || rule.status === "retired") && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[rule.status]}`}>
                  {STATUS_LABEL[rule.status]}
                </span>
              )}
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                {fam.label}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${role.badge}`} title={role.hint}>
                {role.label}
              </span>
            </div>
            <h1 className="mt-3 break-keep text-2xl font-black tracking-tight text-slate-950 sm:text-3xl dark:text-slate-50">
              {rule.title ?? rule.name}
            </h1>
            <p className="mt-2 break-keep text-sm font-medium text-slate-500 dark:text-slate-400">{fam.hint}</p>
            <p className="mt-3 text-sm leading-relaxed text-slate-700 dark:text-slate-200">{rule.description}</p>
            <p className="mt-3 font-mono text-[11px] text-slate-400 dark:text-slate-500">{rule.name}</p>
          </div>
          {action}
        </div>
        <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500 dark:border-slate-800 dark:bg-[#202027] dark:text-slate-400">
          {measure ? MEASURE_HELP : STATUS_HELP[rule.status]}
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-5">
          <Panel title="날짜별 평균 수익" icon={<BarChart3 className="h-4 w-4" />}>
            {chartData.length > 0 ? (
              <>
                <p className="mb-3 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  최근 {chartData.length}일
                </p>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <ReferenceLine y={0} stroke="#cbd5e1" />
                      <XAxis dataKey="date" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 9 }} width={32} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                      <Bar dataKey="mean" radius={[2, 2, 0, 0]}>
                        {chartData.map((d, i) => (
                          <Cell key={i} fill={TONE_FILL[retTone(d.mean)]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </>
            ) : (
              <p className="rounded-xl bg-slate-50 px-3 py-8 text-center text-sm text-slate-400 dark:bg-[#202027]">
                아직 날짜별 검증 데이터가 없습니다.
              </p>
            )}
          </Panel>

          <Panel title="종목 선정 조건" icon={<ListChecks className="h-4 w-4" />}>
            <div className="flex flex-wrap gap-2">
              {rule.predicate.map((c, i) => (
                <span
                  key={i}
                  className="rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-[#202027] dark:text-slate-300"
                >
                  {condText(c)}
                </span>
              ))}
            </div>
            <p className="mt-3 text-[11px] font-medium text-slate-400">
              성적 계산 방식: {exitLabelText(rule.exit_label)}
            </p>
          </Panel>

          {matchedHistory && matchedHistory.length > 0 && (
            <Panel title="날짜별 매칭 기록" icon={<CalendarDays className="h-4 w-4" />}>
              <p className="mb-3 text-xs leading-relaxed text-slate-400 dark:text-slate-500">
                조건에 걸린 종목과 결과를 날짜별로 보여줍니다(최근 {matchedHistory.length}일).
                종목별 수익률은 거래비용 차감 전 원본이고, 날짜 평균만 비용을 뺀 값입니다.
              </p>
              <div className="space-y-2">
                {matchedHistory.map((day, idx) => (
                  <details
                    key={day.report_date}
                    open={idx === 0}
                    className="group rounded-xl border border-slate-200 dark:border-slate-700"
                  >
                    <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-xl px-3 py-2.5 text-xs hover:bg-slate-50 dark:hover:bg-[#202027]">
                      <span className="font-bold text-slate-700 dark:text-slate-200">{day.report_date}</span>
                      <span className="text-slate-400">{day.n_matched}종목</span>
                      <span className="text-slate-400">
                        평균{" "}
                        <span className={`font-bold tabular-nums ${TONE_TEXT[retTone(day.mean_net_ret)]}`}>
                          {fmtPct(day.mean_net_ret)}
                        </span>
                      </span>
                      <span className="ml-auto text-[10px] text-slate-300 transition-transform group-open:rotate-180 dark:text-slate-600">▼</span>
                    </summary>
                    <div className="border-t border-slate-100 px-3 pb-3 pt-2 dark:border-slate-800">
                      <div className="grid grid-cols-[minmax(0,1fr)_3.2rem_3.2rem_3.2rem] gap-x-2 gap-y-1.5 text-[11px]">
                        <span className="text-[10px] font-bold text-slate-400">종목</span>
                        <span className="text-right text-[10px] font-bold text-slate-400">당일</span>
                        <span className="text-right text-[10px] font-bold text-slate-400">수익</span>
                        <span className="text-right text-[10px] font-bold text-slate-400">익일최저</span>
                        {day.matched.map((m) => (
                          <div key={m.code} className="contents">
                            <span className="flex min-w-0 items-center gap-1.5">
                              <span className="truncate font-semibold text-slate-700 dark:text-slate-200">{m.name}</span>
                              {m.selected === 1 && (
                                <span className="shrink-0 rounded bg-rose-100 px-1 text-[9px] font-bold text-rose-600 dark:bg-rose-500/15 dark:text-rose-300" title="현행 점수 상위 10 선정 종목">
                                  톱10
                                </span>
                              )}
                            </span>
                            <span className={`text-right font-semibold tabular-nums ${TONE_TEXT[retTone(m.change_pct ?? null)]}`}>
                              {fmtPct(m.change_pct ?? null)}
                            </span>
                            <span className={`text-right font-bold tabular-nums ${TONE_TEXT[retTone(m.ret)]}`}>
                              {fmtPct(m.ret)}
                            </span>
                            <span className={`text-right tabular-nums ${TONE_TEXT[retTone(m.low)]}`}>
                              {fmtPct(m.low)}
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="mt-2.5 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
                        당일 = 매칭 당일 등락률 · 수익 = {exitLabelText(rule.exit_label)} · 익일최저 = 다음날 장중 최저가 기준(꼬리 리스크)
                      </p>
                    </div>
                  </details>
                ))}
              </div>
            </Panel>
          )}
        </div>

        <aside className="space-y-5">
          <Panel title="누적 성적" icon={<Activity className="h-4 w-4" />}>
            {s && s.n > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {[
                  { l: STAT_META.n.label, v: `${s.n}회` },
                  { l: STAT_META.n_days.label, v: s.n_days != null ? `${s.n_days}일` : "—" },
                  { l: STAT_META.mean_net.label, v: fmtPct(s.mean_net), tone: retTone(s.mean_net) },
                  { l: STAT_META.win_rate.label, v: s.win_rate !== null ? `${Math.round(s.win_rate * 100)}%` : "—" },
                  { l: STAT_META.ci_low.label, v: fmtPct(s.ci_low), tone: retTone(s.ci_low) },
                ].map((x) => (
                  <div key={x.l} className="rounded-xl bg-slate-50 p-3 dark:bg-[#202027]">
                    <p className="text-[10px] font-bold text-slate-400">{x.l}</p>
                    <p className={`mt-1 text-lg font-black tabular-nums ${x.tone ? TONE_TEXT[x.tone] : "text-slate-800 dark:text-slate-100"}`}>
                      {x.v}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-xl bg-slate-50 px-3 py-6 text-center text-sm text-slate-400 dark:bg-[#202027]">
                아직 검증 기록이 없습니다.
              </p>
            )}
            {s && (
              <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
                모든 수익률은 세금·수수료 등 거래비용을 뺀 값입니다.
                {s.worst_low_ret !== null && ` · ${STAT_META.worst_low_ret.label} ${fmtPct(s.worst_low_ret)}`}
              </p>
            )}
          </Panel>

          <Panel title="지표 설명" icon={<Target className="h-4 w-4" />}>
            <dl className="space-y-2 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              {(Object.keys(STAT_META) as (keyof typeof STAT_META)[]).map((k) => (
                <div key={k}>
                  <dt className="font-bold text-slate-700 dark:text-slate-200">{STAT_META[k].label}</dt>
                  <dd>{STAT_META[k].help}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          {/* 날짜별 매칭 기록(본문)이 있으면 요약 패널은 중복이라 숨긴다 */}
          {!matchedHistory?.length && latestMatched && (
            <Panel title={`최근 매칭 ${latestMatched.report_date}`} icon={<Target className="h-4 w-4" />}>
              <div className="flex flex-wrap gap-1.5">
                {latestMatched.matched!.slice(0, 12).map((m) => (
                  <span
                    key={m.code}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] dark:border-slate-700 dark:bg-[#202027]"
                  >
                    <span className="text-slate-600 dark:text-slate-300">{m.name}</span>
                    <span className={`font-semibold tabular-nums ${TONE_TEXT[retTone(m.ret)]}`}>{fmtPct(m.ret)}</span>
                  </span>
                ))}
              </div>
            </Panel>
          )}
        </aside>
      </div>
    </div>
  );
}
