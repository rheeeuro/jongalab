/**
 * Trading API 유틸리티 — trading 백엔드(:8002) 호출 공통 래퍼.
 * 모든 백엔드 호출은 Next 서버(서버 컴포넌트 / 라우트 핸들러)에서만 일어난다.
 * 브라우저는 :8002 에 직접 접근하지 못한다(127.0.0.1 바인딩).
 */
import { cookies } from "next/headers";

const API_BASE = process.env.TRADING_API_URL || "http://127.0.0.1:8002";

// httpOnly 세션 쿠키 → 백엔드 인증 헤더. 쿠키 없으면 빈 헤더(→ 백엔드 401).
async function authHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get("trading_session")?.value;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(
  path: string,
  fallback: T,
  options: RequestInit = { cache: "no-store" }
): Promise<T> {
  try {
    const headers = { ...(options.headers || {}), ...(await authHeaders()) };
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!res.ok) return fallback;
    return res.json();
  } catch (e) {
    console.error(`API fetch error (${path}):`, e);
    return fallback;
  }
}

export { API_BASE, authHeaders };
