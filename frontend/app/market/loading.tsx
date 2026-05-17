import { BarChart3, Globe, Landmark, Gem, TrendingUp, Activity } from "lucide-react";

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

function LeaderRowSkeleton() {
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center gap-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
      <div className="flex items-center gap-3">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-14" />
      </div>
    </div>
  );
}

function SummaryCardSkeleton() {
  return (
    <div className="rounded-lg border border-slate-100 p-4 dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-4 w-8 rounded" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Skeleton className="mb-1 h-3 w-8" />
          <Skeleton className="h-4 w-24" />
        </div>
        <div>
          <Skeleton className="mb-1 h-3 w-8" />
          <Skeleton className="h-4 w-24" />
        </div>
      </div>
    </div>
  );
}

export default function DashboardLoading() {
  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-8 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* 헤더 */}
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            <BarChart3 className="h-6 w-6 text-indigo-500" />
            시황 대시보드
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            주요 시장 지표와 주도주 현황을 한눈에 확인하세요.
          </p>
        </div>

        {/* 미국 시장 지수 */}
        <SectionSkeleton
          icon={<Globe className="h-5 w-5 text-blue-500" />}
          title="🇺🇸 미국 시장"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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

        {/* 주도주 */}
        <div className="grid gap-8 lg:grid-cols-2">
          <SectionSkeleton
            icon={<TrendingUp className="h-5 w-5 text-blue-500" />}
            title="🇺🇸 미국 주도주"
          >
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <LeaderRowSkeleton key={i} />
              ))}
            </div>
          </SectionSkeleton>

          <SectionSkeleton
            icon={<TrendingUp className="h-5 w-5 text-red-500" />}
            title="🇰🇷 한국 주도주"
          >
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <LeaderRowSkeleton key={i} />
              ))}
            </div>
          </SectionSkeleton>
        </div>

        {/* AI 투자 리포트 요약 */}
        <div className="grid gap-8 lg:grid-cols-2">
          <SectionSkeleton
            icon={<Activity className="h-5 w-5 text-blue-500" />}
            title="🇺🇸 최근 AI 리포트"
          >
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <SummaryCardSkeleton key={i} />
              ))}
            </div>
          </SectionSkeleton>

          <SectionSkeleton
            icon={<Activity className="h-5 w-5 text-red-500" />}
            title="🇰🇷 최근 AI 리포트"
          >
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <SummaryCardSkeleton key={i} />
              ))}
            </div>
          </SectionSkeleton>
        </div>
      </div>
    </main>
  );
}
