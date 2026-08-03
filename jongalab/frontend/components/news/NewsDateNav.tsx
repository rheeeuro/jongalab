import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * 뉴스 탭 날짜 이동 — 이전/다음 **영업일**과 '오늘' 바로가기.
 *
 * 달력 하루씩 옮기지 않고 리포트가 존재하는 날짜 목록(`/api/stock-report/dates`) 위를 걷는다.
 * 주말·휴장일에는 재료 목록이 통째로 비어 사용자가 "고장났나" 하게 되는데, 그 날짜를 아예
 * 밟지 않는 편이 놀람이 적다. 요청된 날짜가 목록에 없어도(직접 URL 입력) 목록과 비교해
 * 가장 가까운 앞/뒤 영업일을 찾아 이동은 계속 동작하게 한다.
 *
 * 모바일 우선: 한 줄, 화살표는 44px 터치 타깃.
 */
export function NewsDateNav({ date, dates }: { date: string; dates: string[] }) {
  // dates 는 최신순(내림차순). 더 과거 = 더 뒤, 더 최신 = 더 앞.
  const sorted = [...dates].sort((a, b) => (a < b ? 1 : -1));
  const prev = sorted.find((d) => d < date) ?? null;
  const next = [...sorted].reverse().find((d) => d > date) ?? null;
  const latest = sorted[0] ?? null;

  const label = formatKoDate(date);
  const isLatest = latest !== null && date === latest;

  return (
    <div className="flex items-center gap-1">
      <NavArrow href={prev ? `/news?date=${prev}` : null} dir="prev" />
      <span className="flex min-w-0 items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-bold tabular-nums text-slate-700 dark:bg-slate-800 dark:text-slate-200">
        <CalendarDays className="h-3.5 w-3.5 shrink-0 text-slate-400" />
        {label}
      </span>
      <NavArrow href={next ? `/news?date=${next}` : null} dir="next" />
      {!isLatest && latest && (
        <Link
          href="/news"
          className="ml-1 shrink-0 rounded-full px-2.5 py-1.5 text-xs font-bold text-emerald-600 transition-colors hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950/40"
        >
          최신
        </Link>
      )}
    </div>
  );
}

function NavArrow({ href, dir }: { href: string | null; dir: "prev" | "next" }) {
  const Icon = dir === "prev" ? ChevronLeft : ChevronRight;
  const label = dir === "prev" ? "이전 영업일" : "다음 영업일";
  const cls =
    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors";
  if (!href) {
    return (
      <span aria-hidden className={`${cls} text-slate-200 dark:text-slate-700`}>
        <Icon className="h-5 w-5" />
      </span>
    );
  }
  return (
    <Link
      href={href}
      aria-label={label}
      className={`${cls} text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100`}
    >
      <Icon className="h-5 w-5" />
    </Link>
  );
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-08-03" → "8/3(월)". 서버·클라 렌더가 갈리지 않게 UTC 기준으로 파싱한다. */
export function formatKoDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  const dow = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${m}/${d}(${dow})`;
}
