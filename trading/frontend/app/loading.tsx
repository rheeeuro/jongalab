import { fmtDate, todayYYYYMMDD } from "@/lib/format";

// app/page.tsx 는 /health·/summary·/positions·/day·/names 를 서버에서 모두 await 한 뒤에야
// 렌더된다. 그 사이 이 loading.tsx 가 즉시 표시된다. (느린 /buy-preview 는 페이지 안에서
// <Suspense> 로 분리돼 있어 이 스켈레톤을 붙잡지 않는다.) 데이터가 없어도 확정인 것(오늘 날짜·섹션 타이틀·라벨)은 실제 값으로 그리고,
// 값이 오는 부분만 스켈레톤 바로 둬서 실제 페이지와의 시프트를 최소화한다.
export default function Loading() {
  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      {/* 날짜 — 서버 데이터 불필요, 실제 값 표기 */}
      <p className="text-sm text-slate-500">{fmtDate(todayYYYYMMDD())}</p>

      {/* 히어로: 오늘 실현 손익 */}
      <section className="mt-2">
        <h1 className="text-[15px] font-medium text-slate-500">오늘 실현 손익</h1>
        {/* 손익 금액 */}
        <Bar className="mt-1.5 h-10 w-56" />
        {/* 청산 원금 대비 안내 */}
        <Bar className="mt-2 h-3 w-40" />
        {/* 모드·자동매매 배지 */}
        <div className="mt-3 flex flex-wrap gap-2">
          <Bar className="h-7 w-20 rounded-full" />
          <Bar className="h-7 w-28 rounded-full" />
        </div>
      </section>

      {/* 오늘 청산한 종목 — 타이틀은 실제, 개수·합계·행은 스켈레톤 */}
      <Card title="오늘 청산한 종목">
        <Bar className="-mt-1 mb-2 h-3 w-32" /> {/* "어제 매수가 → 오늘 매도가" 캡션 */}
        <Rows n={3} />
      </Card>

      {/* 보유 중인 종목 */}
      <Card title="보유 중인 종목">
        <Rows n={2} />
      </Card>

      {/* 오늘 요약 (2열) — 라벨은 실제, 값만 스켈레톤 */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <MiniStat label="오늘 주문 수" />
        <MiniStat label="보유 종목 수" />
      </div>

      <span className="sr-only">불러오는 중…</span>
    </main>
  );
}

/* ---------- 스켈레톤 프리미티브 (page.tsx 의 Card/MiniStat className 과 일치) ---------- */

function Bar({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-slate-200 dark:bg-slate-800 ${className}`}
    />
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h2 className="shrink-0 text-base font-bold">{title}</h2>
        {/* 개수·합계 (n종목 · ₩…) */}
        <Bar className="h-4 w-24" />
      </div>
      {children}
    </section>
  );
}

function Rows({ n }: { n: number }) {
  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {Array.from({ length: n }).map((_, i) => (
        <li key={i} className="flex items-center justify-between py-3">
          <div className="min-w-0 space-y-1.5">
            <Bar className="h-4 w-28" /> {/* 종목명 */}
            <Bar className="h-3 w-20" /> {/* 코드·평단 등 */}
          </div>
          <div className="space-y-1.5 text-right">
            <Bar className="ml-auto h-4 w-16" /> {/* 수량·현재가 */}
            <Bar className="ml-auto h-3 w-12" /> {/* 손익·단가 */}
          </div>
        </li>
      ))}
    </ul>
  );
}

function MiniStat({ label }: { label: string }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm dark:bg-slate-900">
      <p className="text-xs text-slate-400">{label}</p>
      <Bar className="mt-1.5 h-6 w-16" />
    </div>
  );
}
