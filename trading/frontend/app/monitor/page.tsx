import { apiFetch } from "@/lib/api";
import type { MonitorState, NameMap } from "@/types";
import MonitorView from "@/components/MonitorView";

export const dynamic = "force-dynamic";

const FALLBACK: MonitorState = {
  active: false,
  in_window: false,
  phase: null,
  worker: null,
  last_poll_at: null,
  poll_sec: 15,
  hard_stop_pct: 2,
  trail_pct: 1,
  pullback_pct: 0.5,
  positions: [],
  orders: [],
  events: [],
};

export default async function MonitorPage() {
  const [monitor, names] = await Promise.all([
    apiFetch<MonitorState>("/monitor", FALLBACK),
    apiFetch<NameMap>("/names", {}),
  ]);

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="mb-3 text-xl font-bold">자동매매 모니터</h1>
      <MonitorView initial={monitor} names={names} />
    </main>
  );
}
