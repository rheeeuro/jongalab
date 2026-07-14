import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

// GET /api/macro-events?days=30 — 다가오는 거시 이벤트(FOMC·CPI 등) 프록시
export async function GET(request: NextRequest) {
  try {
    const days = new URL(request.url).searchParams.get('days') ?? '';
    const qs = days ? `?days=${days}` : '';
    const res = await fetch(`${API_BASE}/api/macro-events${qs}`, {
      cache: 'no-store'
    });

    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("macro-events 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
