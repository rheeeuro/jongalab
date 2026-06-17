import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

// GET /api/pnl-monthly?month=YYYYMM — 월별 일자 실현손익 프록시
export async function GET(request: NextRequest) {
  try {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    const qs = month ? `?month=${month}` : "";
    const res = await fetch(`${API_BASE}/pnl/monthly${qs}`, { cache: "no-store" });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("pnl-monthly 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
