import { NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

// GET /api/admin/verify — httpOnly 세션 쿠키 토큰으로 관리자 인증 여부 확인.
// AdminLayout 이 마운트 시 호출해 로그인 폼 노출 여부를 결정한다.
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/admin/verify`, {
      cache: 'no-store',
      headers: await adminAuthHeaders(),
    });
    return NextResponse.json({ ok: res.ok }, { status: res.ok ? 200 : 401 });
  } catch (error) {
    console.error('관리자 verify 프록시 에러:', error);
    return NextResponse.json({ ok: false }, { status: 401 });
  }
}
