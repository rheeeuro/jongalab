import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

// GET /api/market-holidays?month=YYYY-MM — 그 달의 KRX 휴장 평일(이름 포함) 프록시
export async function GET(request: NextRequest) {
  try {
    const month = new URL(request.url).searchParams.get('month') ?? '';
    const res = await fetch(
      `${API_BASE}/api/market-holidays?month=${encodeURIComponent(month)}`,
      { cache: 'no-store' },
    );

    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("market-holidays 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
