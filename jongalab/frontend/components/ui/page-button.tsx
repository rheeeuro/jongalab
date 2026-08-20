import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

/** 페이지 이동 버튼 — 페이지네이션 목록(뉴스 탭 콘텐츠·종목 상세 여론)이 공유한다.
 *  비활성은 링크가 아니라 `span` 이다(누를 수 없는 것에 href 를 주지 않는다). */
export function PageButton({
  href,
  disabled,
  direction,
}: {
  href: string;
  disabled: boolean;
  direction: "prev" | "next";
}) {
  const Icon = direction === "prev" ? ChevronLeft : ChevronRight;
  const className = `flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
    disabled
      ? "cursor-not-allowed bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600"
      : "bg-slate-900 text-white hover:opacity-90 dark:bg-white dark:text-slate-900"
  }`;
  if (disabled) {
    return (
      <span className={className} aria-disabled>
        <Icon className="h-4 w-4" />
      </span>
    );
  }
  return (
    <Link
      href={href}
      className={className}
      aria-label={direction === "prev" ? "이전" : "다음"}
    >
      <Icon className="h-4 w-4" />
    </Link>
  );
}
