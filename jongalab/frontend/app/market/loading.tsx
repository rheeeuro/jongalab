import { BarChart3, Landmark, Gem, Globe } from "lucide-react";

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-slate-200 dark:bg-slate-700 ${className ?? ""}`}
    />
  );
}

function SectionSkeleton({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function IndexCardSkeleton() {
  return (
    <div className="flex h-[104px] flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-7 w-24" />
      <Skeleton className="h-4 w-16" />
    </div>
  );
}

export default function DashboardLoading() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-5 sm:px-6 sm:py-8">
        {/* 헤더 — 실제 화면(page.tsx)과 같은 문구여야 로딩→본문 전환이 튀지 않는다 */}
        <header>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
            <BarChart3 className="h-4 w-4 text-indigo-500" />
            <span>시장 배경</span>
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            시장
          </h1>
          <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
            추천 종목이 놓인 배경 — 지수와 주도 섹터를 나눠서 봅니다.
          </p>
        </header>

        {/* 미국 시장 지수 */}
        <SectionSkeleton
          icon={<Globe className="h-5 w-5 text-blue-500" />}
          title="🇺🇸 미국 시장"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <IndexCardSkeleton key={i} />
            ))}
          </div>
        </SectionSkeleton>

        {/* 한국 시장 지수 */}
        <SectionSkeleton
          icon={<Landmark className="h-5 w-5 text-red-500" />}
          title="🇰🇷 한국 시장"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <IndexCardSkeleton key={i} />
            ))}
          </div>
        </SectionSkeleton>

        {/* 원자재 / 암호화폐 */}
        <SectionSkeleton
          icon={<Gem className="h-5 w-5 text-amber-500" />}
          title="원자재 / 암호화폐"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <IndexCardSkeleton key={i} />
            ))}
          </div>
        </SectionSkeleton>
      </div>
    </main>
  );
}
