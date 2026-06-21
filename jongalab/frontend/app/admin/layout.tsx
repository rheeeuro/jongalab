"use client";

import { useState, useEffect, FormEvent } from "react";
import { Lock, Tags, SlidersHorizontal, Rss, Send, Scale } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ADMIN_TABS = [
  { href: "/admin/tickers", label: "티커 관리", icon: Tags },
  { href: "/admin/sources", label: "소스 관리", icon: Rss },
  { href: "/admin/telegram-users", label: "텔레그램 유저", icon: Send },
  { href: "/admin/settings", label: "전략 설정", icon: SlidersHorizontal },
  { href: "/admin/weight-tuning", label: "가중치 튜닝", icon: Scale },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // httpOnly 세션 쿠키를 백엔드로 검증(콘솔에서 위조 불가). 통과해야 관리 화면 노출.
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/admin/verify", { cache: "no-store" });
        if (!cancelled && res.ok) setAuthenticated(true);
      } catch {
        /* 미인증 → 로그인 폼 */
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        // 로그인 성공 시 서버가 httpOnly 쿠키를 발급함. 별도 클라이언트 저장 불필요.
        setAuthenticated(true);
      } else {
        setError("비밀번호가 올바르지 않습니다.");
      }
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  };

  if (checking) {
    return null;
  }

  if (!authenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm space-y-6 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex flex-col items-center gap-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/30">
              <Lock className="h-6 w-6 text-indigo-500" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
              관리자 로그인
            </h1>
            <p className="text-sm text-slate-500">
              관리 페이지에 접근하려면 비밀번호를 입력하세요.
            </p>
          </div>

          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호"
              autoFocus
              className="w-full rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>

          {error && (
            <p className="text-center text-sm font-medium text-red-500">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-bold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "확인 중..." : "로그인"}
          </button>
        </form>
      </main>
    );
  }

  return <AdminShell>{children}</AdminShell>;
}

function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div>
      <div className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
        <div className="mx-auto max-w-6xl flex items-center gap-1 px-4 sm:px-8 pt-2">
          {ADMIN_TABS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  isActive
                    ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                    : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </div>
      </div>
      {children}
    </div>
  );
}
