import { redirect } from "next/navigation";

// 섹터 랭킹은 시장 탭의 '섹터' 뷰로 병합됐다 — 지수·일정과 같은 '시장 배경' 정보라
// 독립 목적지로 둘 가치가 없었다. sitemap 미포함 경로라 기존 북마크만 넘겨준다.
export default function SectorsPage() {
  redirect("/market?view=sector");
}
