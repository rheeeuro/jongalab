"use client";

import { useEffect, useState } from "react";
import { X, Loader2 } from "lucide-react";
import { fmtDate, hhmmss } from "@/lib/format";
import { eventMeta, eventDetail } from "@/lib/events";
import type { AuditEvent, RoundTrip } from "@/types";

// ISO("2026-06-26T08:01:13") → 날짜 그룹 키("20260626")
const dayKey = (iso: string) => iso.slice(0, 10).replace(/-/g, "");

/** 청산 종목 워커 로그 모달 — audit_log 의 종목별 트레일(매수 집행→스탑 모니터→매도 체결)을 시간순으로.
 *  trip.buy_date(매수일)~date(매도일) 구간을 조회한다. 모바일은 바텀시트, sm+ 는 중앙 모달. */
export default function StockLogModal({
  trip,
  date,
  name,
  onClose,
}: {
  trip: RoundTrip;
  date: string; // 매도(표시) 날짜 YYYYMMDD
  name: string;
  onClose: () => void;
}) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [loading, setLoading] = useState(true);

  // trip 별로 RoundTrips 에서 key 로 remount 되므로 loading/events 는 초기값에서 시작한다.
  useEffect(() => {
    let cancelled = false;
    const start = trip.buy_date ?? date;
    (async () => {
      try {
        const r = await fetch(
          `/api/stock-events?stk_cd=${encodeURIComponent(trip.stk_cd)}&start=${start}&end=${date}`
        );
        if (!cancelled) setEvents(r.ok ? await r.json() : []);
      } catch {
        if (!cancelled) setEvents([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [trip, date]);

  // ESC 닫기 + 배경 스크롤 잠금
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="animate-detail-in relative flex max-h-[80vh] w-full max-w-lg flex-col rounded-t-2xl bg-white shadow-xl dark:bg-slate-900 sm:rounded-2xl">
        {/* 헤더 (고정) */}
        <div className="flex items-start justify-between gap-2 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold">{name}</h2>
            <p className="text-xs text-slate-400">워커 활동 로그</p>
          </div>
          <button
            onClick={onClose}
            aria-label="닫기"
            className="-mr-1.5 shrink-0 rounded-full p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 본문 (스크롤) */}
        <div className="overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex min-h-[160px] items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : !events || events.length === 0 ? (
            <p className="py-12 text-center text-sm text-slate-400">이 종목의 워커 로그가 없어요.</p>
          ) : (
            <ul className="space-y-3">
              {events.map((e, i) => {
                const meta = eventMeta(e.event);
                const detail = eventDetail(e.event, e.payload);
                const showDay = i === 0 || dayKey(e.created_at) !== dayKey(events[i - 1].created_at);
                return (
                  <li key={e.id}>
                    {showDay && (
                      <p className="mb-2 mt-1 text-[11px] font-semibold text-slate-400 first:mt-0">
                        {fmtDate(dayKey(e.created_at))}
                      </p>
                    )}
                    <div className="flex items-start gap-2.5">
                      <span className="mt-0.5 w-[58px] shrink-0 text-xs text-slate-400 tabular-nums">
                        {hhmmss(e.created_at)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold leading-none ${meta.tone}`}>
                          {meta.label}
                        </span>
                        {detail && <p className="mt-0.5 text-xs text-slate-500 tabular-nums dark:text-slate-400">{detail}</p>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
