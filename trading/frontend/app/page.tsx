import Link from "next/link";
import { Settings } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { HealthStatus, Position, TradeSignal, Order, DailySummary } from "@/types";

// 라이브 대시보드 — 매 요청마다 최신 상태를 받는다(정적 프리렌더 비활성).
export const dynamic = "force-dynamic";

function won(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 100_000_000) return `${sign}${(a / 100_000_000).toLocaleString()}억`;
  if (a >= 10_000) return `${sign}${Math.round(a / 10_000).toLocaleString()}만`;
  return `${sign}${a.toLocaleString()}`;
}

// 자동매매 대시보드 메인 — 모바일 우선 레이아웃.
export default async function DashboardPage() {
  const [health, summary, positions, signals, orders] = await Promise.all([
    apiFetch<HealthStatus | null>("/health", null),
    apiFetch<DailySummary | null>("/summary", null),
    apiFetch<Position[]>("/positions", []),
    apiFetch<TradeSignal[]>("/signals", []),
    apiFetch<Order[]>("/orders?limit=20", []),
  ]);

  const pnl = summary?.realized_pnl ?? 0;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <header className="mb-5 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl">자동매매</h1>
          <p className="mt-1 text-sm text-slate-500">집행 · 포지션 · 리스크</p>
        </div>
        <Link
          href="/settings"
          aria-label="리스크 설정"
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
        >
          <Settings className="h-4 w-4" />
          <span className="hidden sm:inline">설정</span>
        </Link>
      </header>

      {/* 상태 요약 */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="모드" value={health?.mode ?? "-"} />
        <StatCard
          label="킬스위치"
          value={health?.kill_switch ? "ON" : "OFF"}
          danger={!!health?.kill_switch}
        />
        <StatCard label="토큰" value={health?.has_token ? "보유" : "없음"} />
        <StatCard label="DB" value={health?.db ? "OK" : "오류"} danger={!health?.db} />
      </section>

      {/* 일일 요약 */}
      <section className="mt-3 grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs text-slate-500">실현손익</div>
          <div
            className={`mt-1 text-lg font-bold tabular-nums ${
              pnl > 0 ? "text-red-600 dark:text-red-400" : pnl < 0 ? "text-blue-600 dark:text-blue-400" : ""
            }`}
          >
            {won(pnl)}
          </div>
        </div>
        <StatCard label="주문수" value={String(summary?.orders_count ?? 0)} />
        <StatCard label="보유종목" value={String(summary?.open_positions ?? 0)} />
      </section>

      {summary?.breaker_tripped && (
        <p className="mt-3 rounded-lg bg-red-50 px-4 py-2.5 text-sm font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
          ⚠️ 서킷브레이커 발동 — 당일 집행 정지됨
        </p>
      )}

      {/* 보유 포지션 */}
      <Section title="보유 포지션">
        {positions.length === 0 ? (
          <Empty>보유 종목이 없습니다.</Empty>
        ) : (
          <ul className="space-y-2">
            {positions.map((p) => {
              const up = p.unrealized_pnl ?? 0;
              return (
                <li key={p.stk_cd} className={rowClass}>
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium">{p.stk_cd}</span>
                    <span className="text-xs text-slate-400 tabular-nums">
                      {p.qty}주 · 평단 {p.avg_price.toLocaleString()}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end tabular-nums">
                    <span className="text-slate-500">
                      {p.cur_prc ? p.cur_prc.toLocaleString() : "-"}
                    </span>
                    <span
                      className={`text-xs font-medium ${
                        up > 0
                          ? "text-red-600 dark:text-red-400"
                          : up < 0
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-slate-400"
                      }`}
                    >
                      {won(up)}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* 오늘의 시그널 */}
      <Section title="오늘의 시그널">
        {signals.length === 0 ? (
          <Empty>오늘 시그널이 없습니다.</Empty>
        ) : (
          <ul className="space-y-2">
            {signals.map((s) => (
              <li key={s.id} className={rowClass}>
                <span className="flex min-w-0 items-center gap-2">
                  <span className="w-5 shrink-0 text-right text-xs text-slate-400">{s.rank_no}</span>
                  <span className="truncate font-medium">{s.stk_nm ?? s.stk_cd}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="tabular-nums text-slate-500">{s.score?.toFixed(1)}</span>
                  <StatusBadge status={s.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* 최근 주문 */}
      <Section title="최근 주문">
        {orders.length === 0 ? (
          <Empty>주문 내역이 없습니다.</Empty>
        ) : (
          <ul className="space-y-2">
            {orders.map((o) => (
              <li key={o.id} className={rowClass}>
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-bold ${
                      o.side === "buy"
                        ? "bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400"
                        : "bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
                    }`}
                  >
                    {o.side === "buy" ? "매수" : "매도"}
                  </span>
                  <span className="truncate font-medium">{o.stk_cd}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2 tabular-nums text-slate-500">
                  {o.qty}주 @ {o.price.toLocaleString()}
                  <StatusBadge status={o.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </main>
  );
}

const rowClass =
  "flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
      {children}
    </p>
  );
}

function StatCard({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-bold tabular-nums ${danger ? "text-red-600 dark:text-red-400" : ""}`}>
        {value}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  done: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  filled: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  pending: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  executing: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  sent: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  intended: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  skipped: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-500",
  rejected: "bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400",
  canceled: "bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400",
  expired: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-500",
};

const STATUS_LABEL: Record<string, string> = {
  done: "완료", filled: "체결", pending: "대기", executing: "집행중", sent: "전송",
  intended: "의도", skipped: "스킵", rejected: "거부", canceled: "취소", expired: "만료",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${
        STATUS_STYLE[status] ?? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      }`}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
