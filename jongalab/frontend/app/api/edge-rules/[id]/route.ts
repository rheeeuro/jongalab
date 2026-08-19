import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

// admin 상태 전이 프록시 — httpOnly 세션 쿠키를 서버에서 백엔드 인증 헤더로 주입한다.
// 조건 미충족 승격은 백엔드가 409 + 사유(detail)를 주며, 여기선 그대로 전달만 한다(조건은 단일 소스).
// pause/resume 은 평소 rule_evaluator 가 자동으로 굴리는 축이고, 여기 경로는 수동 개입용이다.
const ACTIONS = ['promote', 'retire', 'pause', 'resume', 'unretire'] as const;

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { action } = await request.json();
    if (!ACTIONS.includes(action)) {
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
