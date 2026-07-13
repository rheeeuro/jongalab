"use client";

import { useCallback, useEffect, useState } from "react";
import { JobRun, JobRunsResponse, JobRunStatus } from "@/types";
import { ChevronDown, ChevronUp, RefreshCw } from "lucide-react";

// 잡 이름 → 표시 라벨/스케줄 (workers/scheduler.py JOBS 와 동기)
const JOB_META: Record<string, { label: string; schedule: string }> = {
  youtube_collector: { label: "유튜브 수집", schedule: "15분마다" },
  cleanup_content: { label: "콘텐츠 정리", schedule: "매일 04:00" },
  news_ticker_seed: { label: "상장종목 시딩", schedule: "일 07:30" },
  outcome_backfill: { label: "결과 라벨 백필", schedule: "평일 09:30" },
  rule_evaluator: { label: "Edge Ledger 채점", schedule: "평일 09:40" },
  after_hours_labels: { label: "시간외/리스크 라벨", schedule: "평일 17:50" },
  weight_tuner: { label: "가중치 튜너", schedule: "토 08:00" },
};

const STATUS_META: Record<
  JobRunStatus,
  { label: string; dot: string; text: string }
> = {
  success: { label: "성공", dot: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400" },
  fail: { label: "실패", dot: "bg-red-500", text: "text-red-600 dark:text-red-400" },
  timeout: { label: "타임아웃", dot: "bg-orange-500", text: "text-orange-600 dark:text-orange-400" },
  running: { label: "실행 중", dot: "bg-blue-500 animate-pulse", text: "text-blue-600 dark:text-blue-400" },
  aborted: { label: "중단됨", dot: "bg-slate-400", text: "text-slate-500 dark:text-slate-400" },
};

function jobLabel(name: string) {
  return JOB_META[name]?.label ?? name;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  // "YYYY-MM-DD HH:MM:SS" → "MM/DD HH:MM"
  const m = iso.match(/^\d{4}-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[1]}/${m[2]} ${m[3]}:${m[4]}` : iso;
}

function duration(run: JobRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const sec = Math.round(
    (new Date(run.finished_at.replace(" ", "T")).getTime() -
      new Date(run.started_at.replace(" ", "T")).getTime()) / 1000,
  );
  if (sec < 0) return "—";
  if (sec < 60) return `${sec}초`;
  return `${Math.floor(sec / 60)}분 ${sec % 60}초`;
}

export default function JobRunsPage() {
  const [data, setData] = useState<JobRunsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(2);
  const [expanded, setExpanded] = useState<number | null>(null);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/job-runs?days=${days}`, { cache: "no-store" });
      if (res.ok) setData(await res.json());
    } catch (e) {
      console.error("잡 실행 이력 조회 실패:", e);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const latest = data?.latest ?? [];
  const runs = data?.runs ?? [];
  const failCount = runs.filter((r) => r.status === "fail" || r.status === "timeout").length;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100 sm:text-xl">
            워커 실행 현황
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 sm:text-sm">
            스케줄러(jongalab-scheduler)가 실행한 잡 이력
            {failCount > 0 && (
              <span className="ml-1.5 font-semibold text-red-500">· 실패 {failCount}건</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 sm:text-sm"
          >
            <option value={1}>1일</option>
            <option value={2}>2일</option>
            <option value={7}>7일</option>
            <option value={14}>14일</option>
          </select>
          <button
            onClick={fetchRuns}
            disabled={loading}
            aria-label="새로고침"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* 잡별 최신 상태 */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {latest.map((run) => {
          const st = STATUS_META[run.status];
          return (
            <div
              key={run.job_name}
              className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${st.dot}`} />
                  <span className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {jobLabel(run.job_name)}
                  </span>
                </div>
                <span className={`shrink-0 text-xs font-semibold ${st.text}`}>{st.label}</span>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-slate-500">
                <span>{JOB_META[run.job_name]?.schedule ?? run.job_name}</span>
                <span>
                  {fmtTime(run.scheduled_at)} · {duration(run)}
                </span>
              </div>
            </div>
          );
        })}
        {!loading && latest.length === 0 && (
          <p className="col-span-full py-10 text-center text-sm text-slate-500">
            아직 실행 이력이 없습니다. 스케줄러가 첫 잡을 실행하면 여기에 표시됩니다.
          </p>
        )}
      </div>

      {/* 최근 실행 이력 */}
      {runs.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-bold text-slate-700 dark:text-slate-300">
            최근 실행 이력 ({runs.length}건)
          </h2>
          <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
            {runs.map((run) => {
              const st = STATUS_META[run.status];
              const failed = run.status === "fail" || run.status === "timeout";
              const hasDetail = Boolean(run.log_tail);
              const isOpen = expanded === run.id;
              return (
                <div key={run.id}>
                  <button
                    onClick={() => hasDetail && setExpanded(isOpen ? null : run.id)}
                    disabled={!hasDetail}
                    className={`flex w-full items-center gap-2 px-3 py-2.5 text-left ${
                      hasDetail ? "hover:bg-slate-50 dark:hover:bg-slate-800/50" : "cursor-default"
                    }`}
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-800 dark:text-slate-200">
                      {jobLabel(run.job_name)}
                    </span>
                    <span className={`shrink-0 text-xs font-medium ${failed ? st.text : "text-slate-400"}`}>
                      {st.label}
                      {run.exit_code !== null && run.exit_code !== 0 && ` (exit ${run.exit_code})`}
                    </span>
                    <span className="shrink-0 text-xs tabular-nums text-slate-400">
                      {fmtTime(run.scheduled_at)}
                    </span>
                    <span className="hidden shrink-0 text-xs tabular-nums text-slate-400 sm:inline">
                      {duration(run)}
                    </span>
                    {hasDetail &&
                      (isOpen ? (
                        <ChevronUp className="h-4 w-4 shrink-0 text-slate-400" />
                      ) : (
                        <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                      ))}
                  </button>
                  {isOpen && run.log_tail && (
                    <pre className="max-h-64 overflow-auto bg-slate-950 px-3 py-2 text-xs leading-relaxed text-slate-200">
                      {run.log_tail}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </main>
  );
}
