import { apiFetch } from "@/lib/api";
import type { HealthStatus, Position } from "@/types";

// 자동매매 대시보드 메인 — 모바일 우선 레이아웃.
// 스켈레톤: 상태/포지션 요약 카드만. 시그널·주문·감사로그·차트는 추후 확장.
export default async function DashboardPage() {
  const health = await apiFetch<HealthStatus | null>("/health", null);
  const positions = await apiFetch<Position[]>("/positions", []);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <header className="mb-5">
        <h1 className="text-xl font-bold sm:text-2xl">자동매매</h1>
        <p className="mt-1 text-sm text-slate-500">집행 · 포지션 · 리스크</p>
      </header>

      {/* 상태 요약 — 모바일 2열, 데스크탑 4열 */}
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

      {/* 보유 포지션 */}
      <section className="mt-6">
        <h2 className="mb-2 text-base font-semibold">보유 포지션</h2>
        {positions.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
            보유 종목이 없습니다.
          </p>
        ) : (
          <ul className="space-y-2">
            {positions.map((p) => (
              <li
                key={p.stk_cd}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900"
              >
                <span className="font-medium">{p.stk_cd}</span>
                <span className="tabular-nums text-slate-500">
                  {p.qty}주 · 평단 {p.avg_price.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function StatCard({
  label,
  value,
  danger = false,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs text-slate-500">{label}</div>
      <div
        className={`mt-1 text-lg font-bold tabular-nums ${
          danger ? "text-red-600 dark:text-red-400" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}
