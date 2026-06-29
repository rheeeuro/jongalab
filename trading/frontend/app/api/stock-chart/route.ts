import { NextRequest, NextResponse } from "next/server";
import { API_BASE, authHeaders } from "@/lib/api";

// GET /api/stock-chart?stk_cd=&start=YYYYMMDD&end=YYYYMMDD — 1분봉(매수날 12시~매도날 12시) 프록시
export async function GET(request: NextRequest) {
  try {
    const sp = new URL(request.url).searchParams;
    const qs = new URLSearchParams({
      stk_cd: sp.get("stk_cd") ?? "",
      start: sp.get("start") ?? "",
    });
    const end = sp.get("end");
    if (end) qs.set("end", end);
    const res = await fetch(`${API_BASE}/stock-chart?${qs.toString()}`, {
      cache: "no-store",
      headers: await authHeaders(),
    });
    if (!res.ok) return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("stock-chart 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
