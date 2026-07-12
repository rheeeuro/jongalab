// monitor/page.tsx 는 /monitor·/names 를 서버에서 await 한 뒤 렌더된다. 그 사이 이 스켈레톤이
// 즉시 표시된다(없으면 상위 app/loading.tsx 인 '오늘' 레이아웃이 잘못 노출됨).
// 타이틀·섹션명은 확정이라 실제 텍스트로, 값이 오는 부분만 스켈레톤 바로 둔다.
export default function Loading() {
  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="mb-3 text-xl font-bold">자동매매 모니터</h1>

      <div className="space-y-4">
        {/* 상태 헤더 */}
        <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-slate-300 dark:bg-slate-700" />
              <Bar className="h-5 w-28" />
            </div>
            <Bar className="h-9 w-9 rounded-full" />
          </div>
          <Bar className="mt-2.5 h-3 w-64" />
        </section>

        {/* 보유 중 */}
        <Card title="보유 중">
          <Rows n={2} />
        </Card>

        {/* 폴링 활동 로그 */}
        <Card title="폴링 활동 로그">
          <LogRows n={3} />
        </Card>

        {/* 오늘 주문 로그 */}
        <Card title="오늘 주문 로그">
          <Rows n={2} />
        </Card>
      </div>

      <span className="sr-only">불러오는 중…</span>
    </main>
  );
}

function Bar({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-md bg-slate-200 dark:bg-slate-800 ${className}`} />
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-900">
      <h2 className="mb-2 text-base font-bold">{title}</h2>
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
            <Bar className="h-4 w-28" />
            <Bar className="h-3 w-20" />
          </div>
          <div className="space-y-1.5 text-right">
            <Bar className="ml-auto h-4 w-16" />
            <Bar className="ml-auto h-3 w-12" />
          </div>
        </li>
      ))}
    </ul>
  );
}

// 폴링 로그: 좌측 시각(고정폭) + 우측 이벤트 텍스트
function LogRows({ n }: { n: number }) {
  return (
    <ul className="space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <li key={i} className="flex gap-2">
          <Bar className="mt-0.5 h-3 w-[52px] shrink-0" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Bar className="h-4 w-40" />
            <Bar className="h-3 w-24" />
          </div>
        </li>
      ))}
    </ul>
  );
}
