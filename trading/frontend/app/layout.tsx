import type { Metadata } from "next";
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
      <body className="antialiased">{children}</body>
    </html>
  );
}
