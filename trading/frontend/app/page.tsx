import { apiFetch } from "@/lib/api";
import { won, wonExact, pnlClass, pct, fmtDate, todayYYYYMMDD } from "@/lib/format";
import type { HealthStatus, Position, DayDetail, DailySummary, NameMap, BuyPreview } from "@/types";
import RoundTrips from "@/components/RoundTrips";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  // 매수 예정 탭은 매수 윈도우대(15:00~20:00)에만 노출 — 그 밖엔 키움 호출도 생략.
  // (KRX 15:00~15:20 / NXT 19:30~19:50 을 포함하는 구간. 매수 완료로 pending 이 비면 탭은 자동으로 사라짐)
  const inPreviewWindow = new Date().getHours() >= 15 && new Date().getHours() < 20;
  const [health, summary, positions, day, names, preview] = await Promise.all([
    apiFetch<HealthStatus | null>("/health", null),
    apiFetch<DailySummary | null>("/summary", null),
    apiFetch<Position[]>("/positions", []),
    apiFetch<DayDetail | null>("/day", null),
    apiFetch<NameMap>("/names", {}),
    inPreviewWindow ? apiFetch<BuyPreview | null>("/buy-preview", null) : Promise.resolve(null),
  ]);

  const pnl = summary?.realized_pnl ?? 0;
  const invested = day?.invested ?? 0;
  const fees = day?.fees?.total ?? summary?.fees?.total ?? 0; // 당일 수수료+세금 (실현손익엔 이미 반영됨)
  const pnlPct = pct(pnl, invested); // 청산 원금 대비 수익률 (원금 0이면 null)
  const nm = (code: string) => names[code] || code;
  const buys = day?.buys ?? [];
  const trips = day?.roundtrips ?? [];
  const tripsTotal = trips.reduce((s, t) => s + t.sell_qty * t.sell_price, 0); // 매도금액 합계
  const buysTotal = buys.reduce((s, o) => s + (o.filled_qty || o.qty) * (o.fill_price ?? o.price), 0); // 매수금액 합계(체결수량 기준)
  const posTotal = positions.reduce((s, p) => s + (p.eval_amt ?? (p.cur_prc ?? 0) * p.qty), 0); // 평가금액 합계
  const live = health?.mode === "live";
  const auto = !health?.kill_switch; // 킬스위치 OFF = 자동매매 작동중
  const previewVenues = (preview?.venues ?? []).filter((v) => v.stocks.length > 0);
  const previewTotal = previewVenues.reduce((s, v) => s + v.invested, 0); // 예상 매수금액 합계
  const previewCount = previewVenues.reduce((s, v) => s + v.count, 0); // 매수 예정 종목 수
  // 윈도우대 안 + 아직 집행 대기(pending) 종목이 있을 때만 노출. 매수가 끝나면 pending 이 비어 사라짐.
  const showPreview = inPreviewWindow && previewVenues.length > 0;

  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <p className="text-sm text-slate-500">{fmtDate(todayYYYYMMDD())}</p>

      {/* 히어로: 오늘 실현손익 */}
      <section className="mt-2">
        <h1 className="text-[15px] font-medium text-slate-500">오늘 실현 손익</h1>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <p className={`text-4xl font-extrabold tracking-tight ${pnlClass(pnl)}`}>
            {won(pnl)}
          </p>
          {pnlPct && (
            <span className={`text-lg font-bold tabular-nums ${pnlClass(pnl)}`}>
              {pnlPct}
            </span>
          )}
        </div>
        {pnlPct && (
          <p className="mt-1 text-xs text-slate-400 tabular-nums">
            청산 원금 {wonExact(invested)} 대비
          </p>
        )}
        {fees > 0 && (
          <p className="mt-0.5 text-xs text-slate-400 tabular-nums">
            수수료·세금 {wonExact(fees)} 차감 후 순손익
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={live ? "rose" : "slate"}>{live ? "실전투자" : "모의투자"}</Badge>
          <Badge tone={auto ? "green" : "red"}>{auto ? "자동매매 작동중" : "자동매매 정지"}</Badge>
        </div>
      </section>

      {/* 오늘 청산 결과 — 어제 산 종목을 오늘 얼마에 팔았나 (오늘 실현손익의 출처) */}
      <Card title="오늘 청산한 종목" count={trips.length} total={tripsTotal}>
        {trips.length === 0 ? (
          <Empty>오늘 청산한 종목이 없어요.</Empty>
        ) : (
          <>
            <p className="-mt-1 mb-1 text-xs text-slate-400">어제 매수가 → 오늘 매도가</p>
            <RoundTrips trips={trips} names={names} />
          </>
        )}
      </Card>

      {/* 오늘 매수 종목 — 없으면 카드 숨김 */}
      {buys.length > 0 && (
        <Card title="오늘 매수한 종목" count={buys.length} total={buysTotal}>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {buys.map((o) => (
              <li key={o.id} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{nm(o.stk_cd)}</p>
                  <p className="text-xs text-slate-400">{o.stk_cd}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">{o.filled_qty || o.qty}주</p>
                  <p className="text-xs text-slate-400 tabular-nums">{wonExact(o.fill_price ?? o.price)}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* 오늘 매수 예정 — pending 시그널을 거래소별로 시드 배분한 예상 수량(실시간 미리보기).
          매수 윈도우대(15~20시)에 아직 집행 대기 종목이 있을 때만 노출. */}
      {showPreview && (
        <Card title="오늘 매수 예정" count={previewCount} total={previewTotal}>
          <div className="space-y-4">
            <p className="-mt-1 text-xs text-slate-400 tabular-nums">
              가용현금 {wonExact(preview?.cash ?? 0)} 기준 예상 배분
            </p>
            {previewVenues.map((v) => (
              <div key={v.exchange}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold leading-none ${
                        v.exchange === "NXT"
                          ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300"
                          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      {v.exchange}
                    </span>
                    <span className="text-xs text-slate-400 tabular-nums">{v.window}</span>
                  </div>
                  <span className="min-w-0 truncate text-right text-xs text-slate-400 tabular-nums">
                    시드 {wonExact(v.seed)}
                  </span>
                </div>
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {v.stocks.map((s) => {
                    const buying = s.shares >= 1;
                    return (
                      <li
                        key={s.stk_cd}
                        className={`flex items-center justify-between gap-2 py-3 ${buying ? "" : "opacity-50"}`}
                      >
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 truncate font-semibold">
                            {s.rank_no != null && (
                              <span className="shrink-0 text-xs font-bold text-slate-400 tabular-nums">
                                {s.rank_no}
                              </span>
                            )}
                            <span className="truncate">{nm(s.stk_cd)}</span>
                          </p>
                          <p className="text-xs text-slate-400 tabular-nums">
                            {s.stk_cd} · {s.score.toFixed(1)}점
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          {buying ? (
                            <>
                              <p className="font-semibold tabular-nums">{s.shares}주</p>
                              <p className="text-xs text-slate-400 tabular-nums">
                                {wonExact(s.cost)}
                              </p>
                            </>
                          ) : (
                            <p className="text-xs text-slate-400">{s.note ?? "매수 안 함"}</p>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
            <p className="text-[11px] leading-relaxed text-slate-400">
              현재가·가용현금 기준 예상치입니다. 실제 수량은 매수 윈도우(KRX 15:00 / NXT 19:30) 시점에 확정돼요.
            </p>
          </div>
        </Card>
      )}

      {/* 보유 중 — 없으면 카드 숨김 */}
      {positions.length > 0 && (
        <Card title="보유 중인 종목" count={positions.length} total={posTotal}>
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
                    <p className="flex items-center justify-end gap-1 font-semibold tabular-nums">
                      {p.is_nxt && p.cur_prc ? (
                        <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-bold leading-none text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                          NXT
                        </span>
                      ) : null}
                      {p.cur_prc ? wonExact(p.cur_prc) : "-"}
                    </p>
                    <p className={`text-xs font-semibold tabular-nums ${pnlClass(up)}`}>{won(up)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

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

function Card({
  title,
  count,
  total,
  children,
}: {
  title: string;
  count?: number;
  total?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h2 className="shrink-0 text-base font-bold">{title}</h2>
        {count !== undefined && count > 0 && (
          <span className="min-w-0 truncate text-right text-sm font-medium text-slate-400 tabular-nums">
            {count}종목
            {total !== undefined && ` · ${wonExact(total)}`}
          </span>
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
