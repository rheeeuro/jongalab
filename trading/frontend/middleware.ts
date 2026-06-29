import { NextRequest, NextResponse } from "next/server";

// 서버단 접속 게이트. 세션 쿠키가 없으면 페이지 렌더링 전에 /login 으로 보낸다
// (데이터가 담긴 RSC 페이로드 자체를 미인증 클라이언트에 내보내지 않음).
// 실제 데이터 보호는 백엔드 토큰 검증이 담당하며, 미들웨어는 UX 리다이렉트용이다.
export function middleware(req: NextRequest) {
  const hasSession = Boolean(req.cookies.get("trading_session")?.value);
  const { pathname } = req.nextUrl;

  if (!hasSession && pathname !== "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (hasSession && pathname === "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

// /api, 정적 자원은 미들웨어 제외(라우트 핸들러는 자체적으로 토큰을 백엔드에 전달).
// public 자산(logo.png 등)도 제외 — 미인증 시 /login 으로 리다이렉트되면
// 파비콘이 깨지고, next/image 옵티마이저가 원본을 못 받아 로고도 깨진다.
export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|logo.png).*)"],
};
