import { apiFetch } from "@/lib/api";
import { wonExact, fmtDate } from "@/lib/format";
import type { Order, NameMap } from "@/types";

export const dynamic = "force-dynamic";

const STATUS_LABEL: Record<string, string> = {
  filled: "체결", sent: "전송", intended: "접수", rejected: "거부",
  canceled: "취소", accepted: "수락",
};

function dateKey(iso: string): string {
  // "2026-06-17T11:52:13" → "20260617"
  return iso.slice(0, 10).replace(/-/g, "");
}
function hhmm(iso: string): string {
  return iso.slice(11, 16);
}

export default async function HistoryPage() {
  const [orders, names] = await Promise.all([
    apiFetch<Order[]>("/orders?limit=200", []),
    apiFetch<NameMap>("/names", {}),
  ]);
  const nm = (c: string) => names[c] || c;

  // 날짜별 그룹 (최신순)
  const groups = new Map<string, Order[]>();
  for (const o of orders) {
    const k = dateKey(o.created_at);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(o);
  }

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="text-xl font-bold">거래 내역</h1>

      {orders.length === 0 ? (
        <p className="mt-10 text-center text-sm text-slate-400">아직 거래 내역이 없어요.</p>
      ) : (
        [...groups.entries()].map(([date, list]) => (
          <section key={date} className="mt-5">
            <p className="mb-2 px-1 text-sm font-semibold text-slate-500">{fmtDate(date)}</p>
            <div className="rounded-2xl bg-white shadow-sm dark:bg-slate-900">
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {list.map((o) => {
                  const buy = o.side === "buy";
                  return (
                    <li key={o.id} className="flex items-center justify-between px-5 py-3.5">
                      <div className="flex min-w-0 items-center gap-3">
                        <span
                          className={`shrink-0 rounded-lg px-2 py-1 text-xs font-bold ${
                            buy
                              ? "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400"
                              : "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400"
                          }`}
                        >
                          {buy ? "매수" : "매도"}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-semibold">{nm(o.stk_cd)}</p>
                          <p className="text-xs text-slate-400 tabular-nums">
                            {hhmm(o.created_at)} · {STATUS_LABEL[o.status] ?? o.status}
                            {o.mode === "paper" ? " · 모의" : ""}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold tabular-nums">{o.qty}주</p>
                        <p className="text-xs text-slate-400 tabular-nums">{wonExact(o.fill_price ?? o.price)}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </section>
        ))
      )}
    </main>
  );
}
