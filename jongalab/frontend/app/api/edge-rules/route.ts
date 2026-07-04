import { NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

// 전략(edge_rule) 목록 프록시 — 관리자 페이지(클라이언트 컴포넌트)가 same-origin 으로 조회.
// 백엔드 GET 은 공개 엔드포인트라 인증 헤더 불필요(변경 POST 는 [id]/route.ts 프록시가 담당).
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/edge-rules`, { cache: 'no-store' });
    const data = await res.json().catch(() => []);
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('edge-rules 목록 프록시 에러:', error);
    return NextResponse.json({ detail: '목록을 불러오지 못했습니다.' }, { status: 500 });
  }
}
