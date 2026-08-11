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
import type { EdgeRule, EdgeRuleDaily, EdgeRuleLatestMatched, EdgeRuleMatchedDay, EdgeRuleWithDaily } from '@/types';

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

// 날짜별 매칭 기록(매칭 있던 날만, 최신→과거) — 상세 페이지 '날짜별 매칭 기록' 섹션용.
export async function getEdgeRuleMatched(id: number, days = 30): Promise<EdgeRuleMatchedDay[]> {
  return apiFetch<EdgeRuleMatchedDay[]>(`/api/edge-rules/${id}/matched?days=${days}`, []);
}

export async function getEdgeRuleWithDailyByName(name: string, days = 60): Promise<EdgeRuleWithDaily | null> {
  const decodedName = decodeURIComponent(name);
  const rules = await getEdgeRules();
  const rule = rules.find((r) => r.name === decodedName);
  if (!rule) return null;
  const { daily, latest_matched } = await getEdgeRuleDaily(rule.id, days);
  return {
    ...rule,
    daily,
    latest_matched,
  };
}

// ── 추천 화면 공통 조회 헬퍼 ──

import type { RecordSummary, StockReport } from '@/types';

/** 리포트가 존재하는 영업일 목록(최신순). 날짜 이동은 이 목록 위를 걷는다. */
export async function getReportDates(limit = 120): Promise<string[]> {
  return apiFetch<string[]>(`/api/stock-report/dates?limit=${limit}`, []);
}

export async function getStockReports(date: string): Promise<StockReport[]> {
  if (!date) return [];
  return apiFetch<StockReport[]>(`/api/stock-report/${date}`, []);
}

export async function getRecordSummary(days = 20): Promise<RecordSummary | null> {
  return apiFetch<RecordSummary | null>(`/api/stock-report/record-summary?days=${days}`, null);
}

/** 룰 슬러그(f5_prog_persistent) → 룰 원본.
 *
 * 픽 카드는 슬러그를 그대로 내지 않고 이 맵으로 **한글 제목**(`title`, 없으면 슬러그)을 찾고,
 * 1등 카드는 여기서 **초심자용 설명(`description`)과 상태**까지 꺼내 선정 근거를 펼친다.
 * 목록 화면이 이미 한 번 부르는 공개 엔드포인트라 추가 왕복이 없다.
 */
export async function getRuleMap(): Promise<Map<string, EdgeRule>> {
  const rules = await getEdgeRules();
  return new Map(rules.map((r) => [r.name, r]));
}

export { API_BASE };
