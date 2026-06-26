"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Activity, CalendarDays, Receipt, Settings } from "lucide-react";

const TABS = [
  { href: "/", label: "오늘", icon: Home },
  { href: "/monitor", label: "모니터", icon: Activity },
  { href: "/calendar", label: "달력", icon: CalendarDays },
  { href: "/history", label: "거래내역", icon: Receipt },
  { href: "/settings", label: "설정", icon: Settings },
];

export function BottomTabs() {
  const pathname = usePathname();
  if (pathname === "/login") return null; // 로그인 화면엔 탭 미노출
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-100 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
      <div className="mx-auto flex max-w-2xl items-stretch justify-around pb-[env(safe-area-inset-bottom)]">
        {TABS.map((t) => {
          const active = t.href === "/" ? pathname === "/" : pathname.startsWith(t.href);
          const Icon = t.icon;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition-colors ${
                active ? "text-slate-900 dark:text-white" : "text-slate-400"
              }`}
            >
              <Icon className="h-5 w-5" strokeWidth={active ? 2.5 : 2} />
              {t.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
