import { NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/weight-tuning/proposals/latest`, {
      cache: 'no-store',
      headers: await adminAuthHeaders(),
    });
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('가중치 제안 조회 프록시 에러:', error);
    return NextResponse.json({ error: '데이터를 가져오지 못했습니다.' }, { status: 500 });
  }
}
