import { redirect } from "next/navigation";

// 콘텐츠 목록은 뉴스 탭의 '콘텐츠' 뷰로 병합됐다 — 뉴스와 같은 '재료' 축이라 독립 목적지로
// 둘 가치가 없었다. sitemap 미포함 경로라 기존 북마크만 넘겨준다.
export default function FeedPage() {
  redirect("/news?view=content");
}
