import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

// POST /api/login — 대시보드 비밀번호 검증 프록시 (백엔드 /admin/login)
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("로그인 프록시 에러:", error);
    return NextResponse.json({ error: "서버에 연결할 수 없습니다." }, { status: 500 });
  }
}
