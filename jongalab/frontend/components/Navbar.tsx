"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NAV_ITEMS, isActiveNav } from "@/lib/nav";

export function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-40 border-b border-slate-100 bg-white/85 backdrop-blur-xl dark:border-slate-900 dark:bg-[#17171C]/85">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-2 px-4 sm:px-6">
        {/* 왼쪽: 로고 */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-6">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-1.5 text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100"
            aria-label="종가랩 홈"
          >
            <Image
              src="/logo.png"
              alt="로고"
              width={24}
              height={24}
              className="rounded-lg"
            />
            {/* 모바일에서도 사이트명을 낸다 — 하단 탭이 화면 이름만 보여주므로
                상단에 브랜드가 없으면 어느 사이트인지 드러나지 않는다.
                (내비 링크는 lg 미만에서 hidden 이라 폭에 여유가 있다) */}
            <span>종가랩</span>
          </Link>

          {/* 데스크톱 (lg+) 메인 네비게이션 — 모바일은 하단 탭바가 담당 */}
          <div className="hidden items-center gap-1 lg:flex">
            {NAV_ITEMS.map((item) => {
              const { href, label, icon: Icon } = item;
              const isActive = isActiveNav(pathname, item);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-bold transition-colors ${
                    isActive
                      ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </div>

        {/* 오른쪽: 테마 + 관리 */}
        <div className="flex shrink-0 items-center gap-1.5">
          <ThemeToggle />

          {/* 하단 탭 5칸이 공개 화면으로 다 차서 '더보기' 시트가 없어졌다 —
              관리 진입점은 모바일에서도 여기서만 닿는다. */}
          <Link
            href="/admin/tickers"
            aria-label="관리"
            className={`flex shrink-0 items-center justify-center rounded-full p-2 transition-colors ${
              pathname.startsWith("/admin")
                ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
                : "text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            }`}
          >
            <Settings className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </nav>
  );
}
