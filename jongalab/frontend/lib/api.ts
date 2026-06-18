/**
 * API 유틸리티 - 백엔드 API 호출 공통 래퍼
 *
 * API Base URL을 한 곳에서 관리하고, 반복되는 try/catch + fetch 패턴을 통합
 */
import { cookies } from 'next/headers';

const API_BASE = process.env.API_URL || 'http://127.0.0.1:8000';

// 관리자 httpOnly 세션 쿠키 → 백엔드 인증 헤더. admin 전용 프록시에서만 사용.
export async function adminAuthHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get('admin_session')?.value;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * 서버 사이드 전용 API fetch 래퍼
 * @param path - API 경로 (예: '/api/contents')
 * @param fallback - 에러 시 반환할 기본값
 * @param options - fetch 옵션 (캐시 전략 등)
 */
export async function apiFetch<T>(
  path: string, 
  fallback: T, 
  options: RequestInit = { cache: 'no-store' }
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
