import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { wonExact, fmtDate } from "@/lib/format";
import type { Order, NameMap } from "@/types";
import ReasonTip from "@/components/ReasonTip";

export const dynamic = "force-dynamic";

const STATUS_LABEL: Record<string, string> = {
  filled: "체결", sent: "전송", intended: "접수", rejected: "거부",
  canceled: "취소", accepted: "수락", skipped: "스킵",
};

function dateKey(iso: string): string {
  // "2026-06-17T11:52:13" → "20260617"
  return iso.slice(0, 10).replace(/-/g, "");
}
function hhmm(iso: string): string {
  return iso.slice(11, 16);
}

/** 표시 전용 병합 행 — 같은 날 반복된 거부/취소 주문을 한 줄로 묶는다. */
interface Row {
  o: Order; // 대표 주문(가장 최근 시도) — 사유·수량·가격은 이 행 기준
  count: number;
  firstAt: string; // 묶음 중 가장 이른 시도 시각
}

/**
 * 하루치 주문(최신순)에서 거부/취소 반복을 (종목·방향·상태) 단위로 한 행에 병합한다.
 * 하한가 매도 거부·IOC 소멸 취소가 15초 폴링마다 수백 행 쌓이는 표시 스팸 방지
 * (2026-07-10 HLB 거부 238건, 07-07 한화오션 취소 55건). 체결/전송/스킵 행은 묶지 않는다.
 * 행 위치는 가장 최근 시도 자리, 시간은 "첫~끝" 범위로 표시한다.
 */
function collapseRepeats(list: Order[]): Row[] {
  const rows: Row[] = [];
  const merged = new Map<string, Row>(); // stk_cd:side:status → 병합 행
  for (const o of list) {
    if (o.status !== "rejected" && o.status !== "canceled") {
      rows.push({ o, count: 1, firstAt: o.created_at });
      continue;
    }
    const key = `${o.stk_cd}:${o.side}:${o.status}`;
    const row = merged.get(key);
    if (row) {
      row.count += 1;
      row.firstAt = o.created_at; // 최신순 순회라 뒤에 온 것이 더 이른 시각
    } else {
      const fresh = { o, count: 1, firstAt: o.created_at };
      merged.set(key, fresh);
      rows.push(fresh);
    }
  }
  return rows;
}

function nowMonth(): string {
  const n = new Date();
  return `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, "0")}`;
}
function shiftMonth(month: string, delta: number): string {
  const y = +month.slice(0, 4);
  const m = +month.slice(4, 6) - 1 + delta;
  const d = new Date(y, m, 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string; w?: string }>;
}) {
  const sp = await searchParams;
  const month = sp.month && /^\d{6}$/.test(sp.month) ? sp.month : nowMonth();
  const y = +month.slice(0, 4);
  const mo = +month.slice(4, 6);

  // 달력(일요일 시작)과 동일한 주차 계산
  const firstDay = new Date(y, mo - 1, 1).getDay(); // 1일의 요일(0=일)
  const daysInMonth = new Date(y, mo, 0).getDate();
  const numWeeks = Math.ceil((firstDay + daysInMonth) / 7);
  const weekOfMonth = (day: number) => Math.ceil((day + firstDay) / 7);

  // 선택 주차 (0 = 전체). w 미지정으로 진입하면 이번 달은 현재 주차, 그 외엔 전체.
  const today = new Date();
  const defaultW =
    month === nowMonth() ? Math.ceil((today.getDate() + firstDay) / 7) : 0;
  const selW =
    sp.w !== undefined && /^\d+$/.test(sp.w)
      ? Math.min(Math.max(+sp.w, 0), numWeeks)
      : defaultW;

  const [allOrders, names] = await Promise.all([
    apiFetch<Order[]>(`/orders?month=${month}`, []),
    apiFetch<NameMap>("/names", {}),
  ]);
  const nm = (c: string) => names[c] || c;

  const orders =
    selW === 0
      ? allOrders
      : allOrders.filter((o) => weekOfMonth(+dateKey(o.created_at).slice(6, 8)) === selW);

  // 날짜별 그룹 (최신순)
  const groups = new Map<string, Order[]>();
  for (const o of orders) {
    const k = dateKey(o.created_at);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(o);
  }

  const chipBase = "shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors";
  const chipOn = "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900";
  const chipOff = "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400";
  const weekHref = (w: number) => `/history?month=${month}&w=${w}`;

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="text-xl font-bold">거래 내역</h1>

      {/* 월 네비 */}
      <section className="mt-4 rounded-2xl bg-white p-4 shadow-sm dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <Link
            href={`/history?month=${shiftMonth(month, -1)}`}
            aria-label="이전 달"
            className="rounded-full p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <ChevronLeft className="h-5 w-5" />
          </Link>
          <span className="text-base font-bold">{y}년 {mo}월</span>
          <Link
            href={`/history?month=${shiftMonth(month, 1)}`}
            aria-label="다음 달"
            className="rounded-full p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <ChevronRight className="h-5 w-5" />
          </Link>
        </div>

        {/* 주차 필터 */}
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          <Link href={weekHref(0)} className={`${chipBase} ${selW === 0 ? chipOn : chipOff}`}>전체</Link>
          {Array.from({ length: numWeeks }, (_, i) => i + 1).map((w) => (
            <Link key={w} href={weekHref(w)} className={`${chipBase} ${selW === w ? chipOn : chipOff}`}>
              {w}주차
            </Link>
          ))}
        </div>
      </section>

      {orders.length === 0 ? (
        <p className="mt-10 text-center text-sm text-slate-400">
          {selW === 0 ? "이 달의 거래 내역이 없어요." : `${selW}주차 거래 내역이 없어요.`}
        </p>
      ) : (
        [...groups.entries()].map(([date, list]) => (
          <section key={date} className="mt-5">
            <p className="mb-2 px-1 text-sm font-semibold text-slate-500">{fmtDate(date)}</p>
            <div className="rounded-2xl bg-white shadow-sm dark:bg-slate-900">
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {collapseRepeats(list).map(({ o, count, firstAt }) => {
                  const buy = o.side === "buy";
                  const filled = o.status === "filled";
                  const skip = o.status === "skipped"; // 주문 행 없는 매수 스킵/차단 → 수량/가격 없음
                  const label = STATUS_LABEL[o.status] ?? o.status;
                  // 병합 행: 시간은 "첫~끝" 범위, 상태는 "거부 ×238" 형태
                  const time =
                    count > 1 && hhmm(firstAt) !== hhmm(o.created_at)
                      ? `${hhmm(firstAt)}~${hhmm(o.created_at)}`
                      : hhmm(o.created_at);
                  return (
                    <li key={`${skip ? "skip" : "order"}-${o.id}`} className="px-5 py-3.5">
                      {/* 주문 본문 — 미체결은 흐리게(기존 디자인). 사유는 상태 텍스트의 hover/탭 툴팁(ReasonTip). */}
                      <div
                        className={`flex items-center justify-between ${
                          filled ? "" : "opacity-45 grayscale"
                        }`}
                      >
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
                              {time} ·{" "}
                              {/* 미체결이면 상태 텍스트에 hover(데스크탑)/탭(모바일) 시 사유 툴팁 */}
                              {!filled && o.reason ? (
                                <ReasonTip label={label} reason={o.reason} />
                              ) : (
                                label
                              )}
                              {count > 1 && (
                                <span className="font-semibold text-slate-500 dark:text-slate-300"> ×{count}</span>
                              )}
                              {o.mode === "paper" ? " · 모의" : ""}
                            </p>
                          </div>
                        </div>
                        {/* 스킵 행은 주문이 아니라 수량/가격이 없다 — 우측 블록 생략 */}
                        {!skip && (
                          <div className="text-right">
                            <p className="font-semibold tabular-nums">{o.filled_qty || o.qty}주</p>
                            <p className="text-xs text-slate-400 tabular-nums">{wonExact(o.fill_price ?? o.price)}</p>
                          </div>
                        )}
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
