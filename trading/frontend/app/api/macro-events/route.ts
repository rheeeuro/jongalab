import { NextRequest, NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/macro-events?month=YYYYMM — 월별 거시 이벤트(FOMC·CPI 등) 프록시 (손익 달력 마커용)
export async function GET(request: NextRequest) {
  try {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    const qs = month ? `?month=${month}` : "";
    const res = await fetch(`${API_BASE}/macro-events${qs}`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("macro-events 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
