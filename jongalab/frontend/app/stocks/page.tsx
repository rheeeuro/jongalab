import { redirect } from "next/navigation";

// '종목 둘러보기' 인덱스는 홈(오늘의 추천)으로 병합됐다 — 같은 날짜의 같은 10종목을
// 두 화면이 보여주던 중복이었다. sitemap 미포함 경로라 기존 북마크만 넘겨준다.
// (종목별 상세 `/stocks/{ticker}` 는 색인 대상이라 그대로 유지한다.)
export default function StocksIndexPage() {
  redirect("/");
}
