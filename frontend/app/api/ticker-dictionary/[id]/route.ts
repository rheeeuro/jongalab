import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

type RouteContext = {
  params: Promise<{ id: string }> | { id: string };
};

// PUT /api/ticker-dictionary/[id] — 티커 수정 프록시
export async function PUT(request: NextRequest, context: RouteContext) {
  try {
    const resolvedParams = await Promise.resolve(context.params);
    const id = resolvedParams.id;
    const body = await request.json();

    const res = await fetch(`${API_BASE}/api/ticker-dictionary/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '백엔드 응답 에러' }));
      return NextResponse.json(err, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('티커 수정 프록시 에러:', error);
    return NextResponse.json({ error: '수정에 실패했습니다.' }, { status: 500 });
  }
}

// DELETE /api/ticker-dictionary/[id] — 티커 삭제 프록시
export async function DELETE(_request: NextRequest, context: RouteContext) {
  try {
    const resolvedParams = await Promise.resolve(context.params);
    const id = resolvedParams.id;

    const res = await fetch(`${API_BASE}/api/ticker-dictionary/${id}`, {
      method: 'DELETE',
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '백엔드 응답 에러' }));
      return NextResponse.json(err, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('티커 삭제 프록시 에러:', error);
    return NextResponse.json({ error: '삭제에 실패했습니다.' }, { status: 500 });
  }
}
