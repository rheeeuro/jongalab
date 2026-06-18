import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

// POST /api/login — 비밀번호를 백엔드(/admin/login)로 검증하고,
// 성공 시 발급된 세션 토큰을 httpOnly 쿠키로 심는다(콘솔 JS로 위조 불가).
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.token) {
      return NextResponse.json(data, { status: res.status || 401 });
    }
    const out = NextResponse.json({ ok: true });
    out.cookies.set("trading_session", data.token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 12, // 12시간
    });
    return out;
  } catch (error) {
    console.error("로그인 프록시 에러:", error);
    return NextResponse.json({ error: "서버에 연결할 수 없습니다." }, { status: 500 });
  }
}
