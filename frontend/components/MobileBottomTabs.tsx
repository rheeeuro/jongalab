"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Sparkles,
  LineChart,
  CandlestickChart,
  Newspaper,
  MoreHorizontal,
  Layers,
  FileText,
  Settings,
  X,
} from "lucide-react";

const PRIMARY_TABS = [
  { href: "/", label: "오늘", icon: Sparkles, match: "exact" as const },
  { href: "/market", label: "시장", icon: LineChart },
  { href: "/stocks", label: "종목", icon: CandlestickChart },
  { href: "/feed", label: "콘텐츠", icon: Newspaper },
];

const MORE_ITEMS = [
  { href: "/sectors", label: "섹터", icon: Layers, desc: "섹터 트렌드 보기" },
  {
    href: "/reports",
    label: "리포트",
    icon: FileText,
    desc: "일일 리포트 아카이브",
  },
  { href: "/admin/tickers", label: "관리", icon: Settings, desc: "관리자" },
];

function isActiveTab(pathname: string, href: string, match?: "exact") {
  if (match === "exact") return pathname === href;
  return pathname.startsWith(href);
}

export function MobileBottomTabs() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentMarket = searchParams.get("market") || "ALL";
  const [moreOpen, setMoreOpen] = useState(false);

  // 경로 변경 시 더보기 시트 자동 닫기
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname, searchParams]);

  // 더보기 시트 열렸을 때 바깥 스크롤 잠금
  useEffect(() => {
    if (moreOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [moreOpen]);

  function buildHref(href: string) {
    if (href === "/feed") return `/feed?market=${currentMarket}&page=1`;
    if (href.startsWith("/admin")) return href;
    return `${href}?market=${currentMarket}`;
  }

  const isMoreActive =
    pathname.startsWith("/sectors") ||
    pathname.startsWith("/reports") ||
    pathname.startsWith("/admin");

  return (
    <>
      {/* 하단 탭바 (lg 미만에서만) */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-100 bg-white/95 backdrop-blur-xl lg:hidden dark:border-slate-900 dark:bg-[#17171C]/95"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-around px-2 py-1.5">
          {PRIMARY_TABS.map(({ href, label, icon: Icon, match }) => {
            const isActive = isActiveTab(pathname, href, match);
            return (
              <Link
                key={href}
                href={buildHref(href)}
                className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1.5 transition-colors ${
                  isActive
                    ? "text-slate-900 dark:text-slate-100"
                    : "text-slate-400 dark:text-slate-500"
                }`}
              >
                <Icon
                  className={`h-5 w-5 ${isActive ? "stroke-[2.5]" : ""}`}
                  strokeWidth={isActive ? 2.5 : 2}
                />
                <span
                  className={`text-[10px] ${isActive ? "font-extrabold" : "font-medium"}`}
                >
                  {label}
                </span>
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            aria-label="더보기"
            className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1.5 transition-colors ${
              isMoreActive
                ? "text-slate-900 dark:text-slate-100"
                : "text-slate-400 dark:text-slate-500"
            }`}
          >
            <MoreHorizontal
              className={`h-5 w-5 ${isMoreActive ? "stroke-[2.5]" : ""}`}
              strokeWidth={isMoreActive ? 2.5 : 2}
            />
            <span
              className={`text-[10px] ${isMoreActive ? "font-extrabold" : "font-medium"}`}
            >
              더보기
            </span>
          </button>
        </div>
      </nav>

      {/* 더보기 바텀시트 */}
      <div
        className={`fixed inset-0 z-50 lg:hidden ${
          moreOpen ? "pointer-events-auto" : "pointer-events-none"
        }`}
      >
        {/* 백드롭 */}
        <div
          className={`absolute inset-0 bg-slate-900/50 backdrop-blur-sm transition-opacity duration-200 ${
            moreOpen ? "opacity-100" : "opacity-0"
          }`}
          onClick={() => setMoreOpen(false)}
        />

        {/* 시트 패널 */}
        <div
          className={`absolute inset-x-0 bottom-0 rounded-t-3xl bg-white shadow-2xl transition-transform duration-300 ease-out dark:bg-[#17171C] ${
            moreOpen ? "translate-y-0" : "translate-y-full"
          }`}
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          {/* 핸들 */}
          <div className="flex justify-center pt-3">
            <div className="h-1.5 w-10 rounded-full bg-slate-200 dark:bg-slate-700" />
          </div>

          <div className="flex items-center justify-between px-6 pt-4 pb-2">
            <h2 className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
              더보기
            </h2>
            <button
              onClick={() => setMoreOpen(false)}
              aria-label="닫기"
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="px-4 pb-6 pt-2">
            <div className="space-y-1.5">
              {MORE_ITEMS.map(({ href, label, icon: Icon, desc }) => {
                const isActive = pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={buildHref(href)}
                    className={`flex items-center gap-4 rounded-2xl px-4 py-3.5 transition-colors ${
                      isActive
                        ? "bg-slate-100 dark:bg-slate-800"
                        : "hover:bg-slate-50 dark:hover:bg-slate-900"
                    }`}
                  >
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                        isActive
                          ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-bold text-slate-900 dark:text-slate-100">
                        {label}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {desc}
                      </p>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
