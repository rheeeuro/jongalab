import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import { Suspense } from "react";
import { Navbar } from "@/components/Navbar";
import { MobileBottomTabs } from "@/components/MobileBottomTabs";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://jongalab.com";

export const metadata: Metadata = {
  // 모든 상대 canonical/openGraph URL의 기준 도메인. www/non-www·쿼리파라미터
  // 변형이 원본으로 통합되도록 각 페이지는 metadataBase 기준 canonical을 선언한다.
  metadataBase: new URL(SITE_URL),
  // 페이지 타이틀 단일 규칙: 각 페이지는 **화면 h1 과 같은 짧은 이름**만 선언하고
  // 브랜드 접미사는 여기서 붙인다(`추천 성적 · 종가랩`). 페이지에서 " — 종가랩" 을
  // 직접 붙이지 말 것 — 접미사가 두 번 붙거나 구분자가 화면마다 달라진다.
  title: {
    default: "종가랩 — 종가 전략 연구소",
    template: "%s · 종가랩",
  },
  description: "AI가 분석해주는 매일의 주식 시장 요약",
  icons: {
    icon: "/logo.png",
    apple: "/logo.png",
  },
  verification: {
    google: "7Mm6OvLkEKXRXU0eZZune2CuZoZwRdKikruNXDMMH6s",
    other: {
      "naver-site-verification": "fd7c7a2a4a893dab722c75eab1ab9255a97ccf56",
      "google-adsense-account": "ca-pub-1583778688623269",
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}var r=document.documentElement;if(t==='dark'){r.classList.add('dark');}r.style.colorScheme=t;}catch(e){}})();`,
          }}
        />
        <Script
          async
          src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1583778688623269"
          crossOrigin="anonymous"
          strategy="afterInteractive"
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} bg-[#F9FAFB] text-slate-900 antialiased dark:bg-[#0F0F12] dark:text-slate-100`}
      >
        <Suspense>
          <Navbar />
        </Suspense>
        {/* 모바일 하단 탭바 높이만큼 패딩 확보 */}
        <div className="pb-20 lg:pb-0">{children}</div>
        <Suspense>
          <MobileBottomTabs />
        </Suspense>
      </body>
    </html>
  );
}
