"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS, isActiveNav } from "@/lib/nav";

/** 모바일 하단 탭 — 목적지 5개가 5칸에 그대로 들어간다.
 *
 * '더보기' 바텀시트를 두지 않는다: 시트에 넣는 순간 그 화면들이 1클릭에서 2클릭이 된다.
 * 화면 수를 줄여 계층 없이 평평하게 유지하는 것이 이 내비의 전제다(`lib/nav.ts`).
 * 상단 Navbar 57px + 이 탭바 ≈61px = 상하 크롬 118px 를 넘기지 않는다.
 */
export function MobileBottomTabs() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-100 bg-white/95 backdrop-blur-xl lg:hidden dark:border-slate-900 dark:bg-[#17171C]/95"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-around px-1 py-1.5">
        {NAV_ITEMS.map((item) => {
          const { href, label, icon: Icon } = item;
          const isActive = isActiveNav(pathname, item);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1.5 transition-colors ${
                isActive
                  ? "text-slate-900 dark:text-slate-100"
                  : "text-slate-400 dark:text-slate-500"
              }`}
            >
              <Icon className="h-5 w-5" strokeWidth={isActive ? 2.5 : 2} />
              <span
                className={`text-[10px] ${isActive ? "font-extrabold" : "font-medium"}`}
              >
                {label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
