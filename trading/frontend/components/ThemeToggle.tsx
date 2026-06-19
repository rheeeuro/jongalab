"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" ? v : null;
}

function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
  root.style.colorScheme = theme;
}

export function ThemeToggle({
  variant = "icon",
  className = "",
}: {
  variant?: "icon" | "row";
  className?: string;
}) {
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // 마운트 후에만 저장값/시스템 테마를 읽어 SSR 하이드레이션 불일치를 피한다.
    const initial = getStoredTheme() ?? getSystemTheme();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(initial);
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    applyTheme(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme, mounted]);

  // 시스템 테마 변경 추적 (사용자가 직접 저장한 값이 없을 때만)
  useEffect(() => {
    if (!mounted) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      if (getStoredTheme() === null) {
        setTheme(e.matches ? "dark" : "light");
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mounted]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  const isDark = theme === "dark";
  const Icon = isDark ? Sun : Moon;
  const label = isDark ? "라이트 모드로 전환" : "다크 모드로 전환";

  if (variant === "row") {
    return (
      <button
        type="button"
        onClick={toggle}
        aria-label={label}
        suppressHydrationWarning
        className={`flex w-full items-center gap-4 rounded-2xl px-4 py-3.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-900 ${className}`}
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1 text-left">
          <p className="font-bold text-slate-900 dark:text-slate-100">
            {mounted && isDark ? "라이트 모드" : "다크 모드"}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            화면 테마 전환
          </p>
        </div>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      suppressHydrationWarning
      className={`flex shrink-0 items-center justify-center rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-300 ${className}`}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}
