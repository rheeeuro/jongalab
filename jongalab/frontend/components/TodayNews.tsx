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

function NewsItem({ item }: { item: NewsMentionItem }) {
  const time = formatTime(item.created_at);
  const { text, href } = parseHeadline(item);
  const inner = (
    <>
      <div className="flex items-center gap-2 text-xs font-medium text-slate-400 dark:text-slate-500">
        {time && <span className="tabular-nums">{time}</span>}
        {item.channel_name && <span className="truncate">{item.channel_name}</span>}
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

  return href ? (
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
  );
}

/**
 * 오늘의 뉴스 — 종목 상세 페이지에서 당일 뉴스 헤드라인을 최신순으로 보여준다.
 * 홈 '오늘 새로 뜬 재료' 카드 클릭 흐름의 목적지. 모바일 우선: 세로 리스트.
 *
 * **시세보도 기사는 접는다** — "급등/상한가/특징주" 류가 실측 21%라 재료 기사가 묻힌다.
 * 그건 재료가 아니라 그날 가격을 옮긴 기사이고(갭상승이 기사를 만드는 역인과), 판별은 백엔드가
 * 후속 재료 채점과 **같은 함수**로 계산해 `is_price_report` 로 실어준다.
 * 접기는 CSS-only(details/summary)로 두어 서버 컴포넌트를 유지한다.
 */
export function TodayNews({ items }: { items: NewsMentionItem[] }) {
  if (!items?.length) return null;

  const material = items.filter((it) => !it.is_price_report);
  const priceOnly = items.filter((it) => it.is_price_report);
  // 전부 시세 기사면 접을 게 없다(빈 화면 방지) — 그대로 본문에 보여준다.
  const main = material.length ? material : priceOnly;
  const folded = material.length ? priceOnly : [];

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
        {main.map((item, idx) => (
          <li key={`${item.source_url ?? ""}-${idx}`}>
            <NewsItem item={item} />
          </li>
        ))}
      </ul>

      {folded.length > 0 && (
        <details className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <summary className="cursor-pointer list-none text-xs font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300">
            시세 기사 {folded.length}건 보기
          </summary>
          <ul className="mt-1 divide-y divide-slate-100 dark:divide-slate-800">
            {folded.map((item, idx) => (
              <li key={`price-${item.source_url ?? ""}-${idx}`} className="opacity-70">
                <NewsItem item={item} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
