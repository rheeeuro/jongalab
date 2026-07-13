import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

// GET /api/job-runs — 스케줄러 잡 실행 이력 프록시 (admin 전용 백엔드에 쿠키 세션 주입)
export async function GET(request: NextRequest) {
  try {
    const days = new URL(request.url).searchParams.get('days');
    const params = days ? `?days=${encodeURIComponent(days)}` : '';

    const res = await fetch(`${API_BASE}/api/job-runs${params}`, {
      cache: 'no-store',
      headers: await adminAuthHeaders(),
    });

    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('잡 실행 이력 프록시 에러:', error);
    return NextResponse.json({ error: '데이터를 가져오지 못했습니다.' }, { status: 500 });
  }
}
