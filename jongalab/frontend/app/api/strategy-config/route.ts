import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/strategy-config`, {
      cache: 'no-store',
      headers: await adminAuthHeaders(),
    });
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('전략 설정 조회 프록시 에러:', error);
    return NextResponse.json({ error: '데이터를 가져오지 못했습니다.' }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/strategy-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(await adminAuthHeaders()) },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('전략 설정 저장 프록시 에러:', error);
    return NextResponse.json({ error: '저장에 실패했습니다.' }, { status: 500 });
  }
}
