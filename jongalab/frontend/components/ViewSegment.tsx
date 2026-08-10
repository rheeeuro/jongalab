import Link from "next/link";
import type { LucideIcon } from "lucide-react";

export type ViewOption = {
  key: string;
  label: string;
  icon: LucideIcon;
  href: string;
};

/** 화면 안에서 뷰를 가르는 세그먼트 (`/market` 지수·섹터, `/news` 뉴스·콘텐츠).
 *
 * **탭(목적지)을 늘리는 대신** 한 화면 안에서만 나누는 장치다 — 목적지는 5개로 고정이고
 * (`lib/nav.ts`) 여기서 갈린 뷰는 쿼리(`?view=`)라 canonical 도 원래 경로 하나로 남는다.
 * 서버 렌더 링크라 JS 없이도 동작한다.
 */
export function ViewSegment({
  options,
  active,
}: {
  options: ViewOption[];
  active: string;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 p-1 dark:bg-slate-800/60">
      {options.map(({ key, label, icon: Icon, href }) => {
        const isActive = active === key;
        return (
          <Link
            key={key}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-extrabold transition-colors ${
              isActive
                ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </Link>
        );
      })}
    </div>
  );
}
