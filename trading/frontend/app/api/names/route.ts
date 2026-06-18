import { NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/names — 종목코드→이름 맵 프록시
export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/names`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) return NextResponse.json({}, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("names 프록시 에러:", error);
    return NextResponse.json({}, { status: 500 });
  }
}
