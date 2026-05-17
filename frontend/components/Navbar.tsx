"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Sparkles,
  LineChart,
  Layers,
  Newspaper,
  CandlestickChart,
  FileText,
  Settings,
  Globe,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "오늘", icon: Sparkles, match: "exact" as const },
  { href: "/market", label: "시장", icon: LineChart },
  { href: "/stocks", label: "종목", icon: CandlestickChart },
  { href: "/sectors", label: "섹터", icon: Layers },
  { href: "/feed", label: "콘텐츠", icon: Newspaper },
  { href: "/reports", label: "리포트", icon: FileText },
];

const MARKET_FILTERS = [
  {
    value: "ALL",
    label: "전체",
    shortLabel: "전체",
    icon: Globe,
    activeClass: "bg-slate-900 text-white dark:bg-white dark:text-slate-900",
  },
  {
    value: "US",
    label: "🇺🇸 미국장",
    shortLabel: "🇺🇸",
    icon: null,
    activeClass: "bg-blue-500 text-white",
  },
  {
    value: "KR",
    label: "🇰🇷 한국장",
    shortLabel: "🇰🇷",
    icon: null,
    activeClass: "bg-rose-500 text-white",
  },
];

const MARKET_FILTER_ROUTES = ["/", "/market", "/feed", "/sectors", "/reports"];

function isMarketFilterRoute(pathname: string) {
  return MARKET_FILTER_ROUTES.some((r) =>
    r === "/" ? pathname === "/" : pathname.startsWith(r),
  );
}

function isActiveNav(pathname: string, href: string, match?: "exact") {
  if (match === "exact") return pathname === href;
  return pathname.startsWith(href);
}

export function Navbar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentMarket = searchParams.get("market") || "ALL";

  const showMarketFilter = isMarketFilterRoute(pathname);

  function marketHref(market: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("market", market);
    if (pathname === "/feed") {
      params.set("page", "1");
    }
    return `${pathname}?${params.toString()}`;
  }

  function buildNavHref(href: string) {
    if (href === "/feed") return `/feed?market=${currentMarket}&page=1`;
    return `${href}?market=${currentMarket}`;
  }

  return (
    <nav className="sticky top-0 z-40 border-b border-slate-100 bg-white/85 backdrop-blur-xl dark:border-slate-900 dark:bg-[#17171C]/85">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-2 px-4 sm:px-6">
        {/* 왼쪽: 로고 */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-6">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-1.5 text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100"
            aria-label="주식 AI 홈"
          >
            <Image
              src="/logo.png"
              alt="로고"
              width={24}
              height={24}
              className="rounded-lg"
            />
            <span className="hidden sm:inline">주식 AI</span>
          </Link>

          {/* 데스크톱 (lg+) 메인 네비게이션 */}
          <div className="hidden lg:flex items-center gap-1">
            {NAV_ITEMS.map(({ href, label, icon: Icon, match }) => {
              const isActive = isActiveNav(pathname, href, match);
              return (
                <Link
                  key={href}
                  href={buildNavHref(href)}
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

        {/* 오른쪽: 시장 필터 + 관리 */}
        <div className="flex shrink-0 items-center gap-1.5">
          {showMarketFilter && (
            <div className="flex items-center gap-1 rounded-full bg-slate-100 p-1 dark:bg-slate-800/60">
              {MARKET_FILTERS.map(
                ({ value, label, shortLabel, icon: Icon, activeClass }) => {
                  const isActive = currentMarket === value;
                  return (
                    <Link
                      key={value}
                      href={marketHref(value)}
                      aria-label={label}
                      className={`flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold transition-all sm:px-3 sm:text-sm ${
                        isActive
                          ? `${activeClass} shadow-sm`
                          : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                      }`}
                    >
                      {Icon && <Icon className="h-3.5 w-3.5" />}
                      <span className="hidden md:inline">{label}</span>
                      <span className="md:hidden">{shortLabel}</span>
                    </Link>
                  );
                },
              )}
            </div>
          )}

          <Link
            href="/admin/tickers"
            aria-label="관리"
            className={`hidden sm:flex shrink-0 items-center justify-center rounded-full p-2 transition-colors ${
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
