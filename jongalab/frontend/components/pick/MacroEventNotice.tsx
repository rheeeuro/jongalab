import type { MacroEvent } from "@/types";
import { CalendarClock } from "lucide-react";

/**
 * 오늘 밤 거시 이벤트 배너 (메인) — 보유 창(지금 → 익일 09:00)에 걸리는 이벤트가 있을 때만 노출.
 * severity 3(FOMC·CPI·고용)은 자동매매 시드가 축소되는 밤이라 주황으로 강조한다.
 */
export function MacroEventNotice({ events }: { events: MacroEvent[] }) {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = ymd(now);
  const hm = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const tomorrow = ymd(new Date(now.getTime() + 86_400_000));

  // 오늘 남은 이벤트 + 내일 새벽(09:00 이전, 예: FOMC 03:00) — 종가베팅 보유 창과 동일 기준
  const tonight = events.filter(
    (ev) => (ev.date === today && ev.time >= hm) || (ev.date === tomorrow && ev.time < "09:00"),
  );
  if (tonight.length === 0) return null;

  const major = tonight.some((ev) => ev.severity >= 3);
  const names = tonight.map((ev) => `${ev.name} ${ev.time}`).join(" · ");

  return (
    <section
      className={`flex items-start gap-2.5 rounded-2xl px-4 py-3 text-sm ${
        major
          ? "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
          : "bg-slate-100/70 text-slate-600 dark:bg-slate-900/60 dark:text-slate-300"
      }`}
    >
      <CalendarClock className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-bold">오늘 밤 {names}</span>
        <span className={major ? "" : "text-slate-400 dark:text-slate-400"}>
          {" "}
          — {major ? "내일 아침 가격이 크게 흔들릴 수 있어요. 자동매매 금액을 줄여서 들어가요" : "내일 아침 가격 참고용이에요(금액은 그대로예요)"}
        </span>
      </p>
    </section>
  );
}
