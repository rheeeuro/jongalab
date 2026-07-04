import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

// admin 승격/은퇴 프록시 — httpOnly 세션 쿠키를 서버에서 백엔드 인증 헤더로 주입한다.
// 조건 미충족 승격은 백엔드가 409 + 사유(detail)를 주며, 여기선 그대로 전달만 한다(조건은 단일 소스).
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { action } = await request.json();
    if (action !== 'promote' && action !== 'retire') {
      return NextResponse.json({ detail: '잘못된 액션' }, { status: 400 });
    }
    const res = await fetch(`${API_BASE}/api/edge-rules/${id}/${action}`, {
      method: 'POST',
      headers: await adminAuthHeaders(),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('edge-rule 처리 프록시 에러:', error);
    return NextResponse.json({ detail: '처리에 실패했습니다.' }, { status: 500 });
  }
}
