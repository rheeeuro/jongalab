import { NextResponse } from "next/server";

// POST /api/logout — 세션 쿠키 제거.
export async function POST() {
  const out = NextResponse.json({ ok: true });
  out.cookies.set("trading_session", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return out;
}
