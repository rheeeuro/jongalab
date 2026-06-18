import { NextRequest, NextResponse } from 'next/server';
import { API_BASE, adminAuthHeaders } from '@/lib/api';

// GET /api/telegram-users — 텔레그램 유저 목록 조회 프록시
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const role = searchParams.get('role');
    const isActive = searchParams.get('is_active');
    const qp = new URLSearchParams();
    if (role) qp.set('role', role);
    if (isActive !== null) qp.set('is_active', isActive);
    const params = qp.toString() ? `?${qp.toString()}` : '';

    const res = await fetch(`${API_BASE}/api/telegram-users${params}`, {
      cache: 'no-store',
      headers: await adminAuthHeaders(),
    });

    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('텔레그램 유저 목록 프록시 에러:', error);
    return NextResponse.json({ error: '데이터를 가져오지 못했습니다.' }, { status: 500 });
  }
}

// POST /api/telegram-users — 텔레그램 유저 생성 프록시
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/telegram-users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await adminAuthHeaders()) },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '백엔드 응답 에러' }));
      return NextResponse.json(err, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('텔레그램 유저 생성 프록시 에러:', error);
    return NextResponse.json({ error: '생성에 실패했습니다.' }, { status: 500 });
  }
}
