import { Newspaper, ExternalLink } from "lucide-react";
import { NewsMentionItem } from "@/types";
import { splitHeadlineUrl } from "@/lib/news";
import { PANEL } from "@/lib/ui";

const KST = "Asia/Seoul";

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: KST,
  });
}

function dateKey(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-CA", { timeZone: KST });
}

function dateLabel(key: string, today: string): string {
  if (key === today) return "오늘";
  return key.slice(5).replace("-", ".");
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

/** 날짜별 묶음 — 최근 며칠을 함께 받으므로 어느 날 기사인지 목록에서 갈려야 한다. */
function NewsGroup({ items, today }: { items: NewsMentionItem[]; today: string }) {
  const groups = new Map<string, NewsMentionItem[]>();
  for (const item of items) {
    const key = dateKey(item.created_at);
    const bucket = groups.get(key);
    if (bucket) bucket.push(item);
    else groups.set(key, [item]);
  }
  const single = groups.size <= 1;

  return (
    <>
      {Array.from(groups.entries()).map(([key, group]) => (
        <div key={key || "unknown"}>
          {!single && (
            <p className="pt-3 text-[11px] font-extrabold text-slate-400 dark:text-slate-500">
              {dateLabel(key, today)}
            </p>
          )}
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {group.map((item, idx) => (
              <li key={`${item.source_url ?? ""}-${idx}`}>
                <NewsItem item={item} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

/**
 * 재료 뉴스 — 종목 상세에서 최근 뉴스 헤드라인을 최신순으로 보여준다.
 * 홈 '오늘 새로 뜬 재료' 카드 클릭 흐름의 목적지.
 *
 * **오늘만 받지 않는다** — 장 마감 후·주말에는 당일 뉴스가 0건이라 섹션 자체가 사라졌다.
 * 최근 며칠(`days`)을 함께 받아 날짜로 묶고, `total` 로 상한에 걸렸는지 밝힌다.
 *
 * **시세보도 기사는 접는다** — "급등/상한가/특징주" 류가 재료 기사를 묻는다.
 * 그건 재료가 아니라 그날 가격을 옮긴 기사이고(갭상승이 기사를 만드는 역인과), 판별은 백엔드가
 * 후속 재료 채점과 **같은 함수**로 계산해 `is_price_report` 로 실어준다.
 * 접기는 CSS-only(details/summary)로 두어 서버 컴포넌트를 유지한다.
 */
export function MaterialNews({
  items,
  total,
  days = 1,
}: {
  items: NewsMentionItem[];
  total?: number;
  days?: number;
}) {
  if (!items?.length) return null;

  const today = new Date().toLocaleDateString("en-CA", { timeZone: KST });
  const material = items.filter((it) => !it.is_price_report);
  const priceOnly = items.filter((it) => it.is_price_report);
  // 전부 시세 기사면 접을 게 없다(빈 화면 방지) — 그대로 본문에 보여준다.
  const main = material.length ? material : priceOnly;
  const folded = material.length ? priceOnly : [];
  const shownCount = items.length;
  const truncated = (total ?? shownCount) > shownCount;

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          <Newspaper className="h-4.5 w-4.5 text-emerald-500" />
          재료 뉴스
        </h2>
        {/* 총건수(`total`)를 숫자로 내지 않는다 — 이 목록의 소스 게이트와 리포트의 '뉴스 N건'
            게이트가 달라 두 화면이 같은 종목에 다른 총계를 내게 된다. 잘렸는지만 밝힌다. */}
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          {days > 1 ? `최근 ${days}일` : "오늘"}{" "}
          <span className="font-bold tabular-nums text-slate-500 dark:text-slate-400">
            {truncated ? `최신 ${shownCount}건` : `${shownCount}건`}
          </span>
        </span>
      </div>

      <div className="mt-1">
        <NewsGroup items={main} today={today} />
      </div>

      {folded.length > 0 && (
        <details className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <summary className="cursor-pointer list-none text-xs font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300">
            시세 기사 {folded.length}건 보기
          </summary>
          <div className="opacity-70">
            <NewsGroup items={folded} today={today} />
          </div>
        </details>
      )}
    </section>
  );
}
