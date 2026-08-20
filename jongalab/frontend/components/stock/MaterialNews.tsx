import Link from "next/link";
import { Newspaper, ExternalLink } from "lucide-react";
import { NewsMentionItem } from "@/types";
import { splitHeadlineUrl } from "@/lib/news";
import { josa } from "@/lib/report";
import { PANEL } from "@/lib/ui";

const KST = "Asia/Seoul";

/** 본문에 낼 재료 기사 수 — 이 섹션은 '요즘 무슨 재료가 있나' 를 답하는 자리고,
 *  기사 목록 자체는 뉴스 탭이 갖는다(아래 '전체 보기'). 6줄이면 옆 카드(수급)와 높이가 맞는다. */
const SHOWN = 6;

/** 접힌 목록에 그릴 최대 줄 수 — 접기는 **필터가 무엇을 걸렀는지 눈으로 확인**하는 자리다.
 *  거른 것 전부(대형주는 40건 넘는다)를 DOM 에 넣으면 열지도 않는 목록이 페이지 무게의 큰 몫이 된다. */
const FOLDED = 8;

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

// 기사 URL 우선, 없으면 텔레그램 원문(source_url)으로 링크.
function parseHeadline(item: NewsMentionItem): { text: string; href: string | null } {
  const { text, url } = splitHeadlineUrl(item.headline ?? "");
  return { text, href: url ?? item.source_url };
}

function NewsItem({ item, today }: { item: NewsMentionItem; today: string }) {
  const time = formatTime(item.created_at);
  const day = dateKey(item.created_at);
  const { text, href } = parseHeadline(item);
  const stamp = day && day !== today ? `${day.slice(5).replace("-", ".")} ${time}` : time;
  const inner = (
    <>
      <div className="flex items-center gap-2 text-xs font-medium text-slate-400 dark:text-slate-500">
        {stamp && <span className="shrink-0 tabular-nums">{stamp}</span>}
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
      className="block py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
    >
      {inner}
    </a>
  ) : (
    <div className="py-2.5">{inner}</div>
  );
}

function NewsList({ items, today }: { items: NewsMentionItem[]; today: string }) {
  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {items.map((item, idx) => (
        <li key={`${item.source_url ?? ""}-${idx}`}>
          <NewsItem item={item} today={today} />
        </li>
      ))}
    </ul>
  );
}

/**
 * 재료 뉴스 — 이 종목 **제목에 이름이 나온** 기사만 본문에 둔다.
 *
 * `news_mention` 은 기사 **본문** 매칭이라 대형주는 종목과 상관없는 기사가 절반을 넘는다
 * (삼성전자 실측: 3일 50건 중 제목 매칭 13건 — 나머지는 시황·타사 기사였다). 그걸 그대로 나열하면
 * 이 섹션이 '이 종목 재료' 가 아니라 증권 뉴스 피드가 된다. 판정 근거는 백엔드가 매칭된 이름으로
 * 계산해 `in_headline` 으로 실어준다.
 *
 * 시세보도 기사(`is_price_report`, "급등/상한가/특징주" 류)도 본문에서 뺀다 — 재료가 아니라 그날
 * 가격을 옮긴 기사다(갭상승이 기사를 만드는 역인과).
 *
 * 접기는 **하나**다 — 제외 이유별로 접기를 나누면 접힌 상자가 둘이 되어 본문보다 커진다.
 * 접기·펼치기는 CSS-only(`details/summary`)라 서버 컴포넌트를 유지한다.
 */
export function MaterialNews({
  items,
  days = 1,
  stockName,
  stockCode,
}: {
  items: NewsMentionItem[];
  days?: number;
  stockName: string;
  stockCode: string;
}) {
  if (!items?.length) return null;

  const today = new Date().toLocaleDateString("en-CA", { timeZone: KST });
  const material = items.filter((it) => it.in_headline && !it.is_price_report);
  const main = material.slice(0, SHOWN);
  const rest = items.filter((it) => !main.includes(it));
  const foldedShown = rest.slice(0, FOLDED);

  return (
    <section className={PANEL}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          <Newspaper className="h-4.5 w-4.5 text-emerald-500" />
          재료 뉴스
        </h2>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          최근 {days}일 · 제목에 {stockName}
          {josa(stockName, "이", "가")} 나온 기사
          {material.length > SHOWN && (
            <span className="font-bold text-slate-500 dark:text-slate-400">
              {" "}
              {material.length}건 중 {SHOWN}건
            </span>
          )}
        </span>
      </div>

      {main.length > 0 ? (
        <div className="mt-1">
          <NewsList items={main} today={today} />
        </div>
      ) : (
        <p className="mt-3 text-sm break-keep text-slate-500 dark:text-slate-400">
          최근 {days}일 안에 제목으로 {stockName}
          {josa(stockName, "을", "를")} 다룬 기사는 없었어요. 아래 접힌 목록은 기사 본문에 이름이
          스친 것들이라 이 종목 재료로 보기 어려워요.
        </p>
      )}

      {rest.length > 0 && (
        <details className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <summary className="cursor-pointer list-none text-xs font-bold text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300">
            제목에 이름이 없거나 시세를 옮긴 기사 {rest.length}건
            {rest.length > FOLDED && ` 중 ${FOLDED}건`} 보기
          </summary>
          <div className="opacity-70">
            <NewsList items={foldedShown} today={today} />
          </div>
        </details>
      )}

      <div className="mt-3 flex items-baseline justify-between gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <p className="text-[11px] break-keep text-slate-400 dark:text-slate-500">
          기사 수집은 본문 이름 매칭이라, 이 목록은 제목 기준으로 한 번 더 걸렀어요.
        </p>
        <Link
          href={`/news?ns=${stockCode}#headlines`}
          className="shrink-0 text-[11px] font-bold text-indigo-600 hover:underline dark:text-indigo-400"
        >
          기사 전체 보기 →
        </Link>
      </div>
    </section>
  );
}
