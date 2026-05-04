import { NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

type RouteContext = {
  params: Promise<{ date: string }> | { date: string };
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { date } = await Promise.resolve(context.params);
    const res = await fetch(`${API_BASE}/api/stock-report/${date}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }

    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("일별 리포트 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
