import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

// GET /api/day?date=YYYYMMDD — 일별 상세 프록시
export async function GET(request: NextRequest) {
  try {
    const date = new URL(request.url).searchParams.get("date") ?? "";
    const qs = date ? `?date=${date}` : "";
    const res = await fetch(`${API_BASE}/day${qs}`, { cache: "no-store" });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("day 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
