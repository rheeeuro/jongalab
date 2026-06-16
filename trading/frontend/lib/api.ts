/**
 * Trading API 유틸리티 — trading 백엔드(:8002) 호출 공통 래퍼.
 * jongalab 프론트의 lib/api.ts 와 동일 패턴(서버 사이드 fetch + fallback).
 */

const API_BASE = process.env.TRADING_API_URL || "http://127.0.0.1:8002";

export async function apiFetch<T>(
  path: string,
  fallback: T,
  options: RequestInit = { cache: "no-store" }
): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, options);
    if (!res.ok) return fallback;
    return res.json();
  } catch (e) {
    console.error(`API fetch error (${path}):`, e);
    return fallback;
  }
}

export { API_BASE };
