"use client";

import { useState, useEffect, FormEvent } from "react";
import { Lock, Loader2 } from "lucide-react";

// 대시보드 접속 게이트 — jongalab admin 과 동일 방식(sessionStorage + 백엔드 비번 검증).
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // 마운트 시 1회 세션 인증여부 확인 (브라우저 상태 읽기 — 의도적)
    /* eslint-disable react-hooks/set-state-in-effect */
    if (sessionStorage.getItem("trading_auth") === "true") setAuthed(true);
    setChecking(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        sessionStorage.setItem("trading_auth", "true");
        setAuthed(true);
      } else {
        setError("비밀번호가 올바르지 않습니다.");
      }
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  if (checking) return null;

  if (!authed) {
    return (
      <main className="flex min-h-screen items-center justify-center px-5">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm space-y-6 rounded-2xl bg-white p-7 shadow-sm dark:bg-slate-900"
        >
          <div className="flex flex-col items-center gap-2">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">
              <Lock className="h-5 w-5" />
            </span>
            <h1 className="text-lg font-bold">자동매매 대시보드</h1>
            <p className="text-sm text-slate-500">비밀번호를 입력하세요</p>
          </div>
          <input
            type="password"
            inputMode="text"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            autoFocus
            className="w-full rounded-xl bg-slate-50 px-4 py-3.5 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:bg-slate-800 dark:text-slate-100"
          />
          {error && <p className="text-center text-sm font-medium text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading || !password}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3.5 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
            로그인
          </button>
        </form>
      </main>
    );
  }

  return <>{children}</>;
}
