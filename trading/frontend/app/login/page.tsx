"use client";

import { useState, FormEvent } from "react";
import Image from "next/image";
import { Lock, Loader2 } from "lucide-react";

// 대시보드 로그인 — 비밀번호를 /api/login 으로 보내 검증하고,
// 성공 시 서버가 httpOnly 세션 쿠키를 발급한다. 그 뒤 전체 새로고침으로
// 미들웨어가 쿠키를 인식해 대시보드를 렌더한다.
export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
        window.location.href = "/";
      } else {
        setError("비밀번호가 올바르지 않습니다.");
        setLoading(false);
      }
    } catch {
      setError("서버에 연결할 수 없습니다.");
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-6 rounded-2xl bg-white p-7 shadow-sm dark:bg-slate-900"
      >
        <div className="flex flex-col items-center gap-2">
          <Image
            src="/logo.png"
            alt="종가랩"
            width={56}
            height={56}
            priority
            className="h-14 w-14 rounded-2xl"
          />
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
