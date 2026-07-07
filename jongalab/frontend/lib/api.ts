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

// ── Edge Ledger (가설 스코어보드) 서버 사이드 조회 헬퍼 ──
// 조회는 공개 엔드포인트라 인증 불필요. 승격/은퇴(admin)는 클라이언트 → 로컬 라우트 핸들러
// (app/api/edge-rules/[id])가 httpOnly 쿠키를 서버에서 주입한다(weight-tuning 과 동일 패턴).
import type { EdgeRule, EdgeRuleDaily, EdgeRuleLatestMatched, EdgeRuleWithDaily } from '@/types';

export async function getEdgeRules(): Promise<EdgeRule[]> {
  return apiFetch<EdgeRule[]>('/api/edge-rules', []);
}

// daily 는 matched 없는 스칼라 시계열, latest_matched 는 상세 뷰용 최신 1일치 매칭 목록.
export async function getEdgeRuleDaily(
  id: number,
  days = 60,
): Promise<{ daily: EdgeRuleDaily[]; latest_matched: EdgeRuleLatestMatched | null }> {
  const res = await apiFetch<{
    rule: EdgeRule;
    daily: EdgeRuleDaily[];
    latest_matched: EdgeRuleLatestMatched | null;
  } | null>(`/api/edge-rules/${id}/daily?days=${days}`, null);
  return { daily: res?.daily ?? [], latest_matched: res?.latest_matched ?? null };
}

export async function getEdgeRuleWithDaily(id: number, days = 60): Promise<EdgeRuleWithDaily | null> {
  const res = await apiFetch<{
    rule: EdgeRule;
    daily: EdgeRuleDaily[];
    latest_matched: EdgeRuleLatestMatched | null;
  } | null>(`/api/edge-rules/${id}/daily?days=${days}`, null);
  if (!res) return null;
  return {
    ...res.rule,
    daily: res.daily,
    latest_matched: res.latest_matched,
  };
}

export { API_BASE };
