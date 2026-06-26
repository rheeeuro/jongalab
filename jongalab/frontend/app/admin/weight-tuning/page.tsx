"use client";

import { useState, useEffect, useCallback } from "react";
import { Check, X, Loader2, ArrowRight, TrendingUp, TrendingDown } from "lucide-react";
import type { WeightTuningProposal, WeightTuningSample, WeightBacktest } from "@/types";

const WEIGHT_LABELS: Record<string, string> = {
  SCORE_SUPPLY_BONUS: "수급 가점",
  SCORE_MA_ALIGNED_BONUS: "정배열 가점",
  SCORE_NEAR_HIGH_BONUS: "신고가 가점",
  SCORE_PREFERRED_VALUE_BONUS: "거래대금 우선 가점",
  SCORE_MIN_VALUE_BONUS: "거래대금 최소 가점",
  SCORE_LEADER_BONUS: "대장주 가점",
  SCORE_EXTRA_SUPPLY_DAY_BONUS: "장기 연속수급 가점",
  THEME_STOCK_BONUS: "테마주 가점",
  CONTENT_SCORE_MAX: "콘텐츠 상한",
};

const STATUS_BADGE: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  approved: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  rejected: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
  expired: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "검토 대기",
  approved: "승인됨",
  rejected: "반려됨",
  expired: "만료됨",
};

function fmtPnl(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toLocaleString()}원`;
}

export default function WeightTuningPage() {
  const [proposal, setProposal] = useState<WeightTuningProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/weight-tuning");
      if (res.ok) {
        const data = await res.json();
        setProposal(data && data.id ? data : null);
      }
    } catch (e) {
      console.error("제안 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(id: number, action: "approve" | "reject") {
    setActing(id);
    setMsg(null);
    try {
      const res = await fetch(`/api/weight-tuning/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (res.ok) {
        setMsg({
          type: "success",
          text: action === "approve" ? "가중치가 전략 설정에 반영되었습니다." : "제안을 반려했습니다.",
        });
        await load();
      } else {
        const e = await res.json().catch(() => ({}));
        setMsg({ type: "error", text: e.detail || "처리에 실패했습니다." });
      }
    } catch {
      setMsg({ type: "error", text: "서버에 연결할 수 없습니다." });
    } finally {
      setActing(null);
      setTimeout(() => setMsg(null), 3500);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-3xl px-4 py-6 space-y-5">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            가중치 튜닝 제안
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            매주 자동매매 실현손익을 분석해 종합점수 가중치 조정안을 만듭니다. 승인 시에만 적용됩니다.
          </p>
        </div>

        {msg && (
          <div
            className={`rounded-lg px-4 py-3 text-sm font-medium ${
              msg.type === "success"
                ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
            }`}
          >
            {msg.text}
          </div>
        )}

        {!proposal ? (
          <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 px-4 py-12 text-center text-sm text-slate-500">
            아직 생성된 제안이 없습니다. 토요일 주간 분석 이후 표시됩니다.
          </div>
        ) : (
          <ProposalCard
            proposal={proposal}
            acting={acting === proposal.id}
            onApprove={() => act(proposal.id, "approve")}
            onReject={() => act(proposal.id, "reject")}
          />
        )}
      </div>
    </main>
  );
}

function ProposalCard({
  proposal,
  acting,
  onApprove,
  onReject,
}: {
  proposal: WeightTuningProposal;
  acting: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const cur = proposal.current_weights || {};
  const prop = proposal.proposed_weights || {};
  const pending = proposal.status === "pending";

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {proposal.week_start} ~ {proposal.week_end}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_BADGE[proposal.status]}`}>
            {STATUS_LABEL[proposal.status]}
          </span>
        </div>
        <span
          className={`text-sm font-bold ${
            proposal.total_realized_pnl >= 0 ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400"
          }`}
        >
          {fmtPnl(proposal.total_realized_pnl)}
        </span>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 divide-x divide-slate-100 dark:divide-slate-800 border-b border-slate-100 dark:border-slate-800">
        <Stat label="표본" value={`${proposal.sample_count}종목`} />
        <Stat label="상승" value={`${proposal.winners_count}`} accent="up" />
        <Stat label="하락" value={`${proposal.losers_count}`} accent="down" />
      </div>

      {/* Weights diff */}
      <div className="px-4 sm:px-5 py-4">
        <h3 className="text-xs font-bold text-slate-500 mb-2">가중치 변경안</h3>
        <div className="space-y-1.5">
          {Object.keys(WEIGHT_LABELS).map((k) => (
            <WeightRow key={k} label={WEIGHT_LABELS[k]} from={cur[k]} to={prop[k]} />
          ))}
        </div>
      </div>

      {/* Backtest validation */}
      {proposal.backtest && <BacktestPanel bt={proposal.backtest} />}

      {/* Rationale */}
      {proposal.rationale && (
        <div className="px-4 sm:px-5 pb-4">
          <h3 className="text-xs font-bold text-slate-500 mb-1.5">GPT 분석 근거</h3>
          <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
            {proposal.rationale}
          </p>
        </div>
      )}

      {/* Dataset table */}
      {proposal.dataset && proposal.dataset.length > 0 && (
        <DatasetTable rows={proposal.dataset} />
      )}

      {/* Actions */}
      {pending && (
        <div className="flex items-center gap-2 px-4 sm:px-5 py-3 border-t border-slate-100 dark:border-slate-800">
          <button
            onClick={onReject}
            disabled={acting}
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            <X className="h-4 w-4" /> 반려
          </button>
          <button
            onClick={onApprove}
            disabled={acting}
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            승인 후 적용
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: "up" | "down" }) {
  const color =
    accent === "up"
      ? "text-red-600 dark:text-red-400"
      : accent === "down"
      ? "text-blue-600 dark:text-blue-400"
      : "text-slate-800 dark:text-slate-200";
  return (
    <div className="px-3 py-3 text-center">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-base font-bold ${color}`}>{value}</div>
    </div>
  );
}

function WeightRow({ label, from, to }: { label: string; from?: number; to?: number }) {
  const changed = from !== undefined && to !== undefined && from !== to;
  const up = changed && (to as number) > (from as number);
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-slate-600 dark:text-slate-400">{label}</span>
      <span className="flex items-center gap-1.5 font-mono tabular-nums">
        <span className="text-slate-400">{from ?? "-"}</span>
        <ArrowRight className="h-3 w-3 text-slate-300" />
        <span
          className={
            !changed
              ? "text-slate-500"
              : up
              ? "font-bold text-red-600 dark:text-red-400"
              : "font-bold text-blue-600 dark:text-blue-400"
          }
        >
          {to ?? "-"}
        </span>
      </span>
    </div>
  );
}

const VERDICT: Record<string, { label: string; cls: string }> = {
  IMPROVES: { label: "개선", cls: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400" },
  WORSENS: { label: "악화", cls: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400" },
  NEUTRAL: { label: "보합", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
  INSUFFICIENT: { label: "표본 부족", cls: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" },
};

function BacktestPanel({ bt }: { bt: WeightBacktest }) {
  const v = VERDICT[bt.verdict] ?? VERDICT.NEUTRAL;
  return (
    <div className="px-4 sm:px-5 pb-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-500">백테스트 검증 (제안 가중치 재적용)</h3>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${v.cls}`}>{v.label}</span>
      </div>
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800">
        <BtRow
          label="승자−패자 점수차"
          hint="클수록 승자를 더 높게 평가 = 좋음"
          from={bt.current.spread}
          to={bt.proposed.spread}
          delta={bt.spread_delta}
        />
        <BtRow
          label="손익 순위상관"
          hint="-1~1, 클수록 점수가 실현손익을 잘 반영"
          from={bt.current.pnl_rank_corr}
          to={bt.proposed.pnl_rank_corr}
          delta={bt.corr_delta}
        />
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{bt.note}</p>
    </div>
  );
}

function BtRow({
  label,
  hint,
  from,
  to,
  delta,
}: {
  label: string;
  hint: string;
  from: number | null;
  to: number | null;
  delta: number | null;
}) {
  const fmt = (x: number | null) => (x === null || x === undefined ? "—" : String(x));
  const up = delta !== null && delta > 0;
  const down = delta !== null && delta < 0;
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-sm text-slate-600 dark:text-slate-300">{label}</div>
        <div className="truncate text-[11px] text-slate-400">{hint}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 font-mono tabular-nums text-sm">
        <span className="text-slate-400">{fmt(from)}</span>
        <ArrowRight className="h-3 w-3 text-slate-300" />
        <span className={up ? "font-bold text-green-600 dark:text-green-400" : down ? "font-bold text-red-600 dark:text-red-400" : "text-slate-500"}>
          {fmt(to)}
        </span>
        {delta !== null && delta !== 0 && (
          <span className={`text-[11px] ${up ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
            ({up ? "+" : ""}
            {delta})
          </span>
        )}
      </div>
    </div>
  );
}

function DatasetTable({ rows }: { rows: WeightTuningSample[] }) {
  return (
    <div className="px-4 sm:px-5 pb-4">
      <h3 className="text-xs font-bold text-slate-500 mb-2">종목별 성과</h3>
      <div className="overflow-x-auto -mx-1">
        <table className="w-full min-w-[460px] text-xs">
          <thead>
            <tr className="text-slate-400 text-left">
              <th className="font-medium py-1.5 pr-2">종목</th>
              <th className="font-medium py-1.5 px-2 text-right">실현손익</th>
              <th className="font-medium py-1.5 px-2 text-right">종합</th>
              <th className="font-medium py-1.5 px-2 text-right">수급</th>
              <th className="font-medium py-1.5 px-2 text-center">대장</th>
              <th className="font-medium py-1.5 px-2 text-center">테마</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => (
              <tr key={`${r.stk_cd}-${r.trade_date}`}>
                <td className="py-1.5 pr-2">
                  <div className="flex items-center gap-1">
                    {r.outcome === "WIN" ? (
                      <TrendingUp className="h-3 w-3 text-red-500 shrink-0" />
                    ) : r.outcome === "LOSS" ? (
                      <TrendingDown className="h-3 w-3 text-blue-500 shrink-0" />
                    ) : null}
                    <span className="font-medium text-slate-700 dark:text-slate-300 truncate max-w-[96px]">
                      {r.name || r.stk_cd}
                    </span>
                  </div>
                </td>
                <td
                  className={`py-1.5 px-2 text-right font-mono tabular-nums ${
                    r.realized_pnl >= 0 ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400"
                  }`}
                >
                  {fmtPnl(r.realized_pnl)}
                </td>
                <td className="py-1.5 px-2 text-right tabular-nums text-slate-600 dark:text-slate-400">{r.score}</td>
                <td className="py-1.5 px-2 text-right tabular-nums text-slate-600 dark:text-slate-400">{r.supply_score}</td>
                <td className="py-1.5 px-2 text-center">{r.is_leader ? "●" : ""}</td>
                <td className="py-1.5 px-2 text-center">{r.is_theme_stock ? "●" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
