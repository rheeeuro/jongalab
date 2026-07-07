"use client";

import type { ReactNode } from "react";
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
import type { EdgeRuleWithDaily } from "@/types";
import {
  familyMeta,
  fmtPct,
  retTone,
  TONE_TEXT,
  TONE_FILL,
  STATUS_LABEL,
  STATUS_BADGE,
  STATUS_HELP,
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

export function EdgeRuleDetailContent({
  rule,
  action,
}: {
  rule: EdgeRuleWithDaily;
  action?: ReactNode;
}) {
  const s = rule.stats;
  const fam = familyMeta(rule.family);
  const chartData = rule.daily.map((d) => ({
    date: d.report_date.slice(5),
    mean: d.mean_net_ret,
    n: d.n_matched,
  }));
  const latestMatched = rule.latest_matched?.matched?.length ? rule.latest_matched : null;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[rule.status]}`}>
              {STATUS_LABEL[rule.status]}
            </span>
            <span className="text-[11px] font-semibold text-slate-400">{fam.label}</span>
          </div>
          <h1 className="mt-1 break-keep text-xl font-extrabold text-slate-900 sm:text-2xl dark:text-slate-100">
            {rule.title ?? rule.name}
          </h1>
          <p className="mt-0.5 break-keep text-xs text-slate-400 dark:text-slate-500">{fam.hint}</p>
          <p className="mt-0.5 font-mono text-[10px] text-slate-400 dark:text-slate-500">{rule.name}</p>
        </div>
        {action}
      </div>

      <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
        {STATUS_HELP[rule.status]}
      </p>
      <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">{rule.description}</p>

      {s && s.n > 0 ? (
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-slate-50 p-3 text-center sm:grid-cols-4 dark:bg-slate-800/50">
          {[
            { l: STAT_META.n.label, v: `${s.n}회` },
            { l: STAT_META.mean_net.label, v: fmtPct(s.mean_net), tone: retTone(s.mean_net) },
            { l: STAT_META.win_rate.label, v: s.win_rate !== null ? `${Math.round(s.win_rate * 100)}%` : "—" },
            { l: STAT_META.ci_low.label, v: fmtPct(s.ci_low), tone: retTone(s.ci_low) },
          ].map((x) => (
            <div key={x.l}>
              <p className="text-[10px] text-slate-400">{x.l}</p>
              <p className={`text-sm font-bold tabular-nums ${x.tone ? TONE_TEXT[x.tone] : "text-slate-700 dark:text-slate-200"}`}>
                {x.v}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-2xl bg-slate-50 p-4 text-center text-sm text-slate-400 dark:bg-slate-800/50">
          아직 검증 기록이 없습니다 ({rule.registered_at} 등록 이후 매 거래일 자동으로 쌓입니다).
        </p>
      )}
      {s && (
        <p className="-mt-2 text-[11px] leading-relaxed text-slate-400">
          모든 수익률은 세금·수수료 등 거래비용을 뺀 값입니다.
          {s.worst_low_ret !== null && ` · ${STAT_META.worst_low_ret.label} ${fmtPct(s.worst_low_ret)}`}
        </p>
      )}

      <details className="rounded-xl border border-slate-100 px-3 py-2 dark:border-slate-800">
        <summary className="cursor-pointer list-none text-xs font-semibold text-slate-500 dark:text-slate-400">
          ⓘ 지표가 무슨 뜻인가요?
        </summary>
        <dl className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
          {(Object.keys(STAT_META) as (keyof typeof STAT_META)[]).map((k) => (
            <div key={k}>
              <dt className="inline font-semibold text-slate-600 dark:text-slate-300">{STAT_META[k].label}: </dt>
              <dd className="inline">{STAT_META[k].help}</dd>
            </div>
          ))}
        </dl>
      </details>

      {chartData.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
            날짜별 평균 수익 · 최근 {chartData.length}일
          </p>
          <div className="h-56 w-full sm:h-64">
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
        </div>
      ) : (
        <p className="text-xs text-slate-400">아직 날짜별 검증 데이터가 없습니다.</p>
      )}

      <div>
        <p className="mb-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
          이 전략이 종목을 고르는 조건 (모두 만족해야 함)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {rule.predicate.map((c, i) => (
            <span
              key={i}
              className="rounded-lg bg-slate-100 px-2 py-1 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {condText(c)}
            </span>
          ))}
        </div>
        <p className="mt-1.5 text-[11px] text-slate-400">
          성적 계산 방식: {exitLabelText(rule.exit_label)}
        </p>
      </div>

      {latestMatched && (
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
            최근 조건에 걸린 종목 ({latestMatched.report_date})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {latestMatched.matched!.slice(0, 12).map((m) => (
              <span
                key={m.code}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-100 px-2 py-1 text-[11px] dark:border-slate-800"
              >
                <span className="text-slate-600 dark:text-slate-300">{m.name}</span>
                <span className={`font-semibold tabular-nums ${TONE_TEXT[retTone(m.ret)]}`}>{fmtPct(m.ret)}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
