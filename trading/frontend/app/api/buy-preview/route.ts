import { NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/buy-preview — 매수 예정 종목 프록시 (모니터가 매수 단계일 때 주기적으로 폴링)
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/buy-preview`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("buy-preview 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
