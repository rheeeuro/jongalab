import { NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/monitor — 모니터 상태 프록시 (클라이언트가 가동 중일 때 주기적으로 폴링)
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/monitor`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("monitor 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
