import { Newspaper, ExternalLink } from "lucide-react";
import { NewsMentionItem } from "@/types";
import { splitHeadlineUrl } from "@/lib/news";

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  });
}

// 기사 URL 우선, 없으면 텔레그램 원문(source_url)으로 링크.
function parseHeadline(item: NewsMentionItem): { text: string; href: string | null } {
  const { text, url } = splitHeadlineUrl(item.headline ?? "");
  return { text, href: url ?? item.source_url };
}

/**
 * 오늘의 뉴스 — 종목 상세 페이지에서 당일 뉴스 헤드라인을 최신순으로 보여준다.
 * 홈 '뉴스 재료' 카드 클릭 흐름의 목적지. 모바일 우선: 세로 리스트.
 */
export function TodayNews({ items }: { items: NewsMentionItem[] }) {
  if (!items?.length) return null;

  return (
    <section className="rounded-3xl bg-white p-5 dark:bg-slate-900/60 sm:p-6">
      <div className="mb-4 flex items-end justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          <Newspaper className="h-5 w-5 text-emerald-500" />
          오늘의 뉴스
        </h2>
        <span className="text-xs font-bold text-slate-400">{items.length}건</span>
      </div>

      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((item, idx) => {
          const time = formatTime(item.created_at);
          const { text, href } = parseHeadline(item);
          const inner = (
            <>
              <div className="flex items-center gap-2 text-xs font-medium text-slate-400 dark:text-slate-500">
                {time && <span className="tabular-nums">{time}</span>}
                {item.channel_name && (
                  <span className="truncate">{item.channel_name}</span>
                )}
              </div>
              <div className="mt-1 flex items-start gap-1.5">
                <p className="min-w-0 flex-1 break-words text-sm font-semibold leading-snug text-slate-800 dark:text-slate-200">
                  {text}
                </p>
                {href && (
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300 dark:text-slate-600" />
                )}
              </div>
            </>
          );

          return (
            <li key={`${item.source_url ?? ""}-${idx}`}>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  {inner}
                </a>
              ) : (
                <div className="py-3">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
