import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

/**
 * 헤드라인 스트림 프록시 — 뉴스 탭 '더 보기'가 클라이언트에서 호출한다.
 * API_BASE(127.0.0.1:8000)는 브라우저에서 닿지 않으므로 다른 화면과 같은 로컬 라우트 패턴을 쓴다.
 */
export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const qs = new URLSearchParams({
    limit: sp.get("limit") ?? "40",
    offset: sp.get("offset") ?? "0",
  });
  const date = sp.get("date");
  if (date) qs.set("date", date);

  try {
    const res = await fetch(`${API_BASE}/api/news/stream?${qs}`, { cache: "no-store" });
    if (!res.ok) {
      return NextResponse.json({ error: "백엔드 응답 에러" }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("뉴스 스트림 프록시 에러:", error);
    return NextResponse.json({ error: "데이터를 가져오지 못했습니다." }, { status: 500 });
  }
}
