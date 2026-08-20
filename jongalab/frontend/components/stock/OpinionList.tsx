import { ExternalLink, MessageCircle, Youtube } from "lucide-react";
import { ContentAnalysis, StockCall } from "@/types";
import { CARD } from "@/lib/ui";

const KST = "Asia/Seoul";

function stamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const today = new Date().toLocaleDateString("en-CA", { timeZone: KST });
  const day = d.toLocaleDateString("en-CA", { timeZone: KST });
  const time = d.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: KST,
  });
  return day === today ? time : `${day.slice(5).replace("-", ".")} ${time}`;
}

/** 이 종목에 대한 방향 — 한 콘텐츠가 여러 종목을 다루므로 **이 종목 항목만** 골라야 한다. */
function callFor(item: ContentAnalysis, code: string): StockCall | null {
  const calls = item.stock_calls ?? [];
  return (
    calls.find((c) => (c.ticker ?? "").split(".")[0] === code) ?? null
  );
}

const STANCE_TONE: Record<string, string> = {
  호재: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  악재: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",
  중립: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

/** 콘텐츠 여론 목록 — 한 줄에 **시각·채널 / 한 줄 요약 / 이 종목 방향**.
 *
 * 카드(`ContentCard`)를 쓰지 않는다. 카드는 분석 전문을 모달로 여는 컴포넌트라 종목 화면에서는
 * 페이지 무게의 대부분을 먹으면서(실측 12장 ≈ 100KB) 정작 **이 종목에 대한 방향**은 안 보였다.
 * 여기 필요한 건 "누가 언제 이 종목을 어느 쪽으로 말했나" 한 줄이고, 분석 전문은 원문 링크와
 * 뉴스 탭 콘텐츠 뷰가 갖는다.
 */
export function OpinionList({
  items,
  code,
}: {
  items: ContentAnalysis[];
  code: string;
}) {
  if (!items.length) return null;

  return (
    <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
      {items.map((item) => {
        const call = callFor(item, code);
        const summary = item.tldr?.trim() || item.title;
        const Icon = item.platform === "youtube" ? Youtube : MessageCircle;
        const iconTone =
          item.platform === "youtube" ? "text-red-500" : "text-blue-500";
        const body = (
          <>
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
              <Icon className={`h-3.5 w-3.5 shrink-0 ${iconTone}`} />
              <span className="shrink-0 tabular-nums">{stamp(item.created_at)}</span>
              <span className="min-w-0 truncate">{item.source_name}</span>
              {call?.stance && (
                <span
                  className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
                    STANCE_TONE[call.stance] ?? STANCE_TONE.중립
                  }`}
                >
                  {call.stance}
                  {call.conviction ? ` 확신${call.conviction}` : ""}
                </span>
              )}
              {item.source_url && (
                <ExternalLink className="h-3 w-3 shrink-0 text-slate-300 dark:text-slate-600" />
              )}
            </div>
            {/* 굵은 줄은 **이 종목에 대한 판단**(`stock_calls[].reason`)이다 — 콘텐츠 대표 요약(`tldr`)을
                앞세우면 여러 종목을 다룬 콘텐츠에서 다른 종목 얘기가 제목처럼 걸린다(삼성전자 화면에
                'SK하이닉스 …' 가 먼저 오는 식). 콘텐츠 전체 요약은 아래 회색 줄로 문맥만 준다. */}
            <p className="mt-1 line-clamp-2 text-sm font-semibold leading-snug break-keep text-slate-800 dark:text-slate-200">
              {call?.reason?.trim() || summary}
              {call?.horizon && (
                <span className="ml-1 align-middle text-[10px] font-bold text-slate-400 dark:text-slate-500">
                  {call.horizon}
                </span>
              )}
            </p>
            {call?.reason?.trim() && (
              <p className="mt-0.5 line-clamp-1 text-[11px] break-keep text-slate-500 dark:text-slate-400">
                {summary}
              </p>
            )}
          </>
        );

        return (
          <li key={item.id}>
            {item.source_url ? (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className={`block h-full ${CARD} p-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40`}
              >
                {body}
              </a>
            ) : (
              <div className={`h-full ${CARD} p-3`}>{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
