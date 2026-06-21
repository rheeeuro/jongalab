import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { action } = await request.json();
    if (action !== 'approve' && action !== 'reject') {
      return NextResponse.json({ error: '잘못된 액션' }, { status: 400 });
    }
    const res = await fetch(
      `${API_BASE}/api/weight-tuning/proposals/${id}/${action}`,
      { method: 'POST', headers: await adminAuthHeaders() }
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error('가중치 제안 처리 프록시 에러:', error);
    return NextResponse.json({ error: '처리에 실패했습니다.' }, { status: 500 });
  }
}
