import { NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

type RouteContext = {
  params: Promise<{ market: string }> | { market: string };
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { market } = await Promise.resolve(context.params);
    const res = await fetch(`${API_BASE}/api/market-leaders/${market}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("주도주 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
