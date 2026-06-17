import { apiFetch } from "@/lib/api";
import { won, wonExact, pnlClass, fmtDate, todayYYYYMMDD } from "@/lib/format";
import type { HealthStatus, Position, DayDetail, DailySummary, NameMap } from "@/types";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const [health, summary, positions, day, names] = await Promise.all([
    apiFetch<HealthStatus | null>("/health", null),
    apiFetch<DailySummary | null>("/summary", null),
    apiFetch<Position[]>("/positions", []),
    apiFetch<DayDetail | null>("/day", null),
    apiFetch<NameMap>("/names", {}),
  ]);

  const pnl = summary?.realized_pnl ?? 0;
  const nm = (code: string) => names[code] || code;
  const buys = day?.buys ?? [];
  const live = health?.mode === "live";
  const auto = !health?.kill_switch; // 킬스위치 OFF = 자동매매 작동중

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <p className="text-sm text-slate-500">{fmtDate(todayYYYYMMDD())}</p>

      {/* 히어로: 오늘 실현손익 */}
      <section className="mt-2">
        <h1 className="text-[15px] font-medium text-slate-500">오늘 실현 손익</h1>
        <p className={`mt-1 text-4xl font-extrabold tracking-tight ${pnlClass(pnl)}`}>
          {won(pnl)}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={live ? "rose" : "slate"}>{live ? "실전투자" : "모의투자"}</Badge>
          <Badge tone={auto ? "green" : "red"}>{auto ? "자동매매 작동중" : "자동매매 정지"}</Badge>
        </div>
      </section>

      {/* 오늘 매수 종목 */}
      <Card title="오늘 매수한 종목" count={buys.length}>
        {buys.length === 0 ? (
          <Empty>오늘 매수한 종목이 없어요.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {buys.map((o) => (
              <li key={o.id} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{nm(o.stk_cd)}</p>
                  <p className="text-xs text-slate-400">{o.stk_cd}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">{o.qty}주</p>
                  <p className="text-xs text-slate-400 tabular-nums">{wonExact(o.price)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 보유 중 */}
      <Card title="보유 중인 종목" count={positions.length}>
        {positions.length === 0 ? (
          <Empty>보유 중인 종목이 없어요.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {positions.map((p) => {
              const up = p.unrealized_pnl ?? 0;
              return (
                <li key={p.stk_cd} className="flex items-center justify-between py-3">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{nm(p.stk_cd)}</p>
                    <p className="text-xs text-slate-400 tabular-nums">
                      {p.qty}주 · 평단 {wonExact(p.avg_price)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold tabular-nums">
                      {p.cur_prc ? wonExact(p.cur_prc) : "-"}
                    </p>
                    <p className={`text-xs font-semibold tabular-nums ${pnlClass(up)}`}>{won(up)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* 오늘 요약 */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <MiniStat label="오늘 주문 수" value={`${summary?.orders_count ?? 0}건`} />
        <MiniStat label="보유 종목 수" value={`${summary?.open_positions ?? 0}개`} />
      </div>

      {summary?.breaker_tripped && (
        <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-600 dark:bg-red-950/40 dark:text-red-400">
          ⚠️ 손실 한도 초과로 오늘 자동매매가 정지되었어요.
        </p>
      )}
    </main>
  );
}

/* ---------- 공통 UI ---------- */

function Card({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-base font-bold">{title}</h2>
        {count !== undefined && count > 0 && (
          <span className="text-sm font-medium text-slate-400">{count}</span>
        )}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-400">{children}</p>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm dark:bg-slate-900">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-bold tabular-nums">{value}</p>
    </div>
  );
}

const TONE: Record<string, string> = {
  slate: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  rose: "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400",
  green: "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400",
  red: "bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400",
};

function Badge({ tone, children }: { tone: keyof typeof TONE | string; children: React.ReactNode }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${TONE[tone] ?? TONE.slate}`}>
      {children}
    </span>
  );
}
