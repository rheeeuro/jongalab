import type { Metadata } from "next";
import { BottomTabs } from "@/components/BottomTabs";
import "./globals.css";

export const metadata: Metadata = {
  title: "종가랩 자동매매",
  description: "자동매매 집행·포지션·리스크 대시보드",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <head>
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover"
        />
      </head>
      <body className="bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        {/* 접속 게이트는 middleware 가 서버단에서 처리(미인증 → /login). */}
        {/* 하단 탭바 높이만큼 패딩 */}
        <div className="pb-24">{children}</div>
        <BottomTabs />
      </body>
    </html>
  );
}
