import { NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api';

// 시장 상세 분봉 차트의 범위 토글(1일/5일/1개월) 클라이언트 refetch 프록시.
export async function GET(
  req: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  const range = new URL(req.url).searchParams.get('range') ?? '5d';
  try {
    const res = await fetch(
      `${API_BASE}/api/market-index-history/${encodeURIComponent(symbol)}?range=${encodeURIComponent(range)}`,
      { cache: 'no-store' },
    );
    if (!res.ok) {
      return NextResponse.json({ error: '백엔드 응답 에러' }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error('프록시 에러:', error);
    return NextResponse.json({ error: '데이터를 가져오지 못했습니다.' }, { status: 500 });
  }
}
