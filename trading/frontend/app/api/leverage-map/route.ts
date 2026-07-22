import { NextRequest, NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/leverage-map — 레버리지 ETF 대체매수 매핑 조회 프록시
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/leverage-map`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("leverage-map 조회 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}

// PUT /api/leverage-map — 매핑 전체 교체 프록시
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/leverage-map`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "백엔드 응답 에러" }));
      return NextResponse.json(err, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("leverage-map 수정 프록시 에러:", error);
    return NextResponse.json({ error: "저장에 실패했습니다." }, { status: 500 });
  }
}
