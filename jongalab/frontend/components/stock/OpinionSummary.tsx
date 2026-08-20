import { MessageCircle, Youtube } from "lucide-react";
import { ContentMentionSummary } from "@/types";
import { INSET } from "@/lib/ui";

/** 여론 요약 — 콘텐츠 목록 위에 놓는 한 줄 집계.
 *
 * 목록을 페이지로 자르면(대형주는 7일 100건 이상) "그래서 여론이 어느 쪽인가"를 첫 화면에서 알 수
 * 없다. 그 답만 집계로 낸다. 방향 막대는 **길이 단독 표시를 하지 않는다** — 건수를 항상 함께 낸다.
 * 색은 국장 관례(호재 빨강 / 악재 파랑)이고, 이건 시스템 판정이 아니라 콘텐츠 작성자들의 의견 분포다.
 */
export function OpinionSummary({ summary }: { summary: ContentMentionSummary }) {
  const { stance } = summary;
  const called = stance.호재 + stance.악재 + stance.중립;
  const bars = [
    { key: "호재", value: stance.호재, bar: "bg-red-500/80", text: "text-red-600 dark:text-red-400" },
    { key: "악재", value: stance.악재, bar: "bg-blue-500/80", text: "text-blue-600 dark:text-blue-400" },
    { key: "중립", value: stance.중립, bar: "bg-slate-400/60", text: "text-slate-500 dark:text-slate-400" },
  ];

  return (
    <div className={`${INSET} px-3 py-2.5`}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[11px] font-bold text-slate-500 dark:text-slate-400">
          최근 {summary.days}일 언급
        </span>
        <span className="text-xl font-black tabular-nums text-slate-800 dark:text-slate-100">
          {summary.total}건
        </span>
        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
          채널 {summary.channels}개
        </span>
        <span className="ml-auto flex items-center gap-2 text-[11px] font-medium text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1">
            <Youtube className="h-3.5 w-3.5 text-red-500" />
            <span className="tabular-nums">{summary.platform.youtube}</span>
          </span>
          <span className="flex items-center gap-1">
            <MessageCircle className="h-3.5 w-3.5 text-blue-500" />
            <span className="tabular-nums">{summary.platform.telegram}</span>
          </span>
        </span>
      </div>

      {called > 0 && (
        <ul className="mt-2 space-y-1.5">
          {bars.map(({ key, value, bar, text }) => (
            <li key={key} className="flex items-center gap-2">
              <span className="w-8 shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                {key}
              </span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-700/70">
                <span
                  className={`block h-full rounded-full ${bar}`}
                  style={{ width: `${Math.round((value / called) * 100)}%` }}
                />
              </span>
              <span
                className={`w-10 shrink-0 text-right text-[11px] font-bold tabular-nums ${text}`}
              >
                {value}건
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-[11px] leading-relaxed break-keep text-slate-400 dark:text-slate-500">
        유튜브·텔레그램 콘텐츠를 AI가 읽고 이 종목을 어느 방향으로 말했는지 센 거예요. 맞는
        의견이라는 뜻이 아니고, 종가베팅 점수와도 별개예요.
      </p>
    </div>
  );
}
