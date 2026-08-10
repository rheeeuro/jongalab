import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

/** YYYY-MM-DD → "8월 7일 (금)". KST 고정 — 서버/클라 렌더 결과를 일치시킨다. */
export function formatReportDate(date: string): string {
  const d = new Date(`${date}T00:00:00+09:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("ko-KR", {
    month: "long",
    day: "numeric",
    weekday: "short",
    timeZone: "Asia/Seoul",
  });
}

/** 리포트 기준일 이동 — 영업일 목록(`dates`, 최신순) 위를 한 칸씩 걷는다.
 *
 * 달력 날짜가 아니라 **리포트가 있는 날**만 밟는다(휴장일에 빈 화면이 뜨지 않게).
 * 현재 날짜는 화면 h1 이 이미 말하므로 버튼에는 **이동할 날짜**를 적는다 — 같은 날짜를
 * 두 번 쓰면 헤더가 중복된다.
 *
 * 과거 날짜의 목적지는 `/reports/{date}` 하나뿐이고, 가장 최근 거래일은 홈이 담당한다 —
 * 같은 내용의 URL 을 둘로 만들지 않는다.
 */
export function DateStepper({ date, dates }: { date: string; dates: string[] }) {
  const i = dates.indexOf(date);
  const newer = i > 0 ? dates[i - 1] : null;
  const older = i >= 0 && i < dates.length - 1 ? dates[i + 1] : null;

  return (
    <div className="flex items-center gap-2">
      <StepLink
        href={older ? `/reports/${older}` : null}
        label={older ? formatReportDate(older) : "이전 없음"}
        side="prev"
      />
      <StepLink
        href={newer ? (newer === dates[0] ? "/" : `/reports/${newer}`) : null}
        label={newer ? formatReportDate(newer) : "최신 거래일"}
        side="next"
      />
    </div>
  );
}

function StepLink({
  href,
  label,
  side,
}: {
  href: string | null;
  label: string;
  side: "prev" | "next";
}) {
  // 터치 타깃 36px 이상 — 모바일에서 날짜 이동이 주 조작이다.
  const base =
    "inline-flex min-h-9 min-w-0 flex-1 items-center gap-1 rounded-full px-3 py-2 text-xs font-bold sm:flex-none";
  const icon =
    side === "prev" ? (
      <ChevronLeft className="h-3.5 w-3.5 shrink-0" />
    ) : (
      <ChevronRight className="h-3.5 w-3.5 shrink-0" />
    );

  if (!href) {
    return (
      <span
        aria-disabled
        className={`${base} justify-center bg-slate-50 text-slate-300 dark:bg-slate-800/40 dark:text-slate-600`}
      >
        {side === "prev" && icon}
        <span className="truncate">{label}</span>
        {side === "next" && icon}
      </span>
    );
  }
  return (
    <Link
      href={href}
      aria-label={`${side === "prev" ? "이전" : "다음"} 거래일 ${label}`}
      className={`${base} justify-center bg-white text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100`}
    >
      {side === "prev" && icon}
      <span className="truncate">{label}</span>
      {side === "next" && icon}
    </Link>
  );
}
