import { NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

type RouteContext = {
  params: Promise<{ ticker: string }> | { ticker: string };
};

// 브라우저 대신 Next.js 서버가 파이썬 백엔드를 찔러주는 역할
export async function GET(request: Request, context: RouteContext) {
  try {
    // Next.js 15+ 대응을 위해 params를 안전하게 가져옵니다
    const resolvedParams = await Promise.resolve(context.params);
    const ticker = resolvedParams.ticker;

    const { searchParams } = new URL(request.url);
    const date = searchParams.get('date');
    const qs = date ? `?date=${encodeURIComponent(date)}` : '';

    const res = await fetch(`${API_BASE}/api/stock-price/${ticker}${qs}`, {
      cache: 'no-store'
    });
    
    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error("프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}