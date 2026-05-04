import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

export async function GET(request: NextRequest) {
  try {
    const limit = request.nextUrl.searchParams.get("limit") ?? "30";
    const res = await fetch(`${API_BASE}/api/stock-report/dates?limit=${encodeURIComponent(limit)}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("리포트 날짜 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
