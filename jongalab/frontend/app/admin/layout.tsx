import type { Metadata } from "next";
import { AdminGate } from "./AdminShell";

// 인증·탭 UI 는 클라이언트(`AdminShell`)가 맡고, 이 서버 레이아웃은 메타데이터만 붙인다 —
// 클라이언트 컴포넌트는 metadata 를 export 할 수 없어서 한 겹 나눴다.
export const metadata: Metadata = {
  title: "관리",
  robots: { index: false, follow: false },
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminGate>{children}</AdminGate>;
}
