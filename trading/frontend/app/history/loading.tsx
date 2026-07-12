import { ChevronLeft, ChevronRight } from "lucide-react";

// history/page.tsx 는 /orders·/names 를 서버에서 await 한 뒤 렌더된다. 그 사이 이 스켈레톤이
// 즉시 표시된다(없으면 상위 app/loading.tsx 인 '오늘' 레이아웃이 잘못 노출됨).
// 타이틀은 실제 텍스트로. 월/주차는 searchParams 에 의존해 여기선 알 수 없어 스켈레톤 처리.
export default function Loading() {
  return (
    <main className="mx-auto w-full max-w-2xl px-5 pt-8">
      <h1 className="text-xl font-bold">거래 내역</h1>

      {/* 월 네비 — 화살표는 확정, 월 라벨·주차 칩은 스켈레톤 */}
      <section className="mt-4 rounded-2xl bg-white p-4 shadow-sm dark:bg-slate-900">
        <div className="flex items-center justify-between">
          <span className="rounded-full p-2 text-slate-300 dark:text-slate-700">
            <ChevronLeft className="h-5 w-5" />
          </span>
          <Bar className="h-5 w-24" />
          <span className="rounded-full p-2 text-slate-300 dark:text-slate-700">
            <ChevronRight className="h-5 w-5" />
          </span>
        </div>
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <Bar key={i} className="h-8 w-16 shrink-0 rounded-full" />
          ))}
        </div>
      </section>

      {/* 날짜별 그룹 2개 */}
      {Array.from({ length: 2 }).map((_, g) => (
        <section key={g} className="mt-5">
          <Bar className="mb-2 ml-1 h-4 w-28" /> {/* 날짜 헤더 */}
          <div className="rounded-2xl bg-white shadow-sm dark:bg-slate-900">
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {Array.from({ length: 3 }).map((_, i) => (
                <li key={i} className="flex items-center justify-between px-5 py-3.5">
                  <div className="flex min-w-0 items-center gap-3">
                    <Bar className="h-7 w-11 shrink-0 rounded-lg" /> {/* 매수/매도 뱃지 */}
                    <div className="min-w-0 space-y-1.5">
                      <Bar className="h-4 w-28" /> {/* 종목명 */}
                      <Bar className="h-3 w-24" /> {/* 시각·상태 */}
                    </div>
                  </div>
                  <div className="space-y-1.5 text-right">
                    <Bar className="ml-auto h-4 w-14" /> {/* 수량 */}
                    <Bar className="ml-auto h-3 w-16" /> {/* 가격 */}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ))}

      <span className="sr-only">불러오는 중…</span>
    </main>
  );
}

function Bar({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-md bg-slate-200 dark:bg-slate-800 ${className}`} />
  );
}
