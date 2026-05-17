import { DailySummary, MentionStats } from "@/types";
import { Sparkles } from "lucide-react";

interface Props {
  summary: DailySummary | null;
  mentionStats: MentionStats | null;
}

function getKstDateLabel() {
  // 서버에서 KST 기준 오늘 날짜를 표시. 서버/클라 차이를 방지하기 위해 ko-KR locale 사용
  const now = new Date();
  return now.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
    timeZone: "Asia/Seoul",
  });
}

function getSentimentTone(stats: MentionStats | null): {
  label: string;
  tone: "bull" | "bear" | "neutral";
  ratio: { bull: number; neutral: number; bear: number };
} {
  if (!stats || !stats.sectors?.length) {
    return {
      label: "데이터 부족",
      tone: "neutral",
      ratio: { bull: 33, neutral: 34, bear: 33 },
    };
  }
  let bull = 0;
  let bear = 0;
  let neutral = 0;
  for (const s of stats.sectors) {
    for (const t of s.tickers) {
      const score = t.avg_sentiment ?? 50;
      const w = t.mention_count;
      if (score >= 60) bull += w;
      else if (score <= 40) bear += w;
      else neutral += w;
    }
  }
  const total = bull + bear + neutral || 1;
  const ratio = {
    bull: Math.round((bull / total) * 100),
    neutral: Math.round((neutral / total) * 100),
    bear: Math.round((bear / total) * 100),
  };
  const tone =
    bull > bear * 1.3 ? "bull" : bear > bull * 1.3 ? "bear" : "neutral";
  const label =
    tone === "bull" ? "강세 우세" : tone === "bear" ? "약세 우세" : "중립";
  return { label, tone, ratio };
}

export function TodayHero({ summary, mentionStats }: Props) {
  const dateLabel = getKstDateLabel();
  const sentiment = getSentimentTone(mentionStats);

  const toneStyle =
    sentiment.tone === "bull"
      ? "from-rose-500 to-orange-500"
      : sentiment.tone === "bear"
        ? "from-sky-500 to-indigo-600"
        : "from-amber-400 to-orange-500";

  return (
    <section>
      {/* 메타 */}
      <div className="flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400">
        <Sparkles className="h-4 w-4 text-indigo-500" />
        <span>오늘의 시장</span>
        <span className="text-slate-300 dark:text-slate-700">·</span>
        <span>{dateLabel}</span>
      </div>

      {/* 헤드라인 */}
      <h1 className="mt-3 text-3xl font-black leading-tight tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl lg:text-5xl">
        AI가 본 오늘의
        <br />
        <span
          className={`bg-gradient-to-r ${toneStyle} bg-clip-text text-transparent`}
        >
          시장 흐름은
        </span>
        <br />
        <span className="text-slate-900 dark:text-slate-100">
          {sentiment.label}
          <span className="text-slate-400 dark:text-slate-500">.</span>
        </span>
      </h1>

      {/* 센티먼트 바 */}
      <div className="mt-6 rounded-3xl bg-white p-5 shadow-sm dark:bg-slate-900/60 sm:p-6">
        <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          <span>시장 감성</span>
          {mentionStats && (
            <span className="font-medium normal-case tracking-normal text-slate-500 dark:text-slate-400">
              최근 {mentionStats.window_hours ?? 24}시간 · 콘텐츠{" "}
              {mentionStats.total_contents}건
            </span>
          )}
        </div>

        <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className="bg-rose-500"
            style={{ width: `${sentiment.ratio.bull}%` }}
            title={`강세 ${sentiment.ratio.bull}%`}
          />
          <div
            className="bg-amber-400"
            style={{ width: `${sentiment.ratio.neutral}%` }}
            title={`중립 ${sentiment.ratio.neutral}%`}
          />
          <div
            className="bg-blue-500"
            style={{ width: `${sentiment.ratio.bear}%` }}
            title={`약세 ${sentiment.ratio.bear}%`}
          />
        </div>

        <div className="mt-3 flex items-center justify-between text-xs font-medium text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-rose-500" />
            강세 {sentiment.ratio.bull}%
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
            중립 {sentiment.ratio.neutral}%
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
            약세 {sentiment.ratio.bear}%
          </span>
        </div>

        {summary?.report_date && (
          <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
            리포트 기준일 · {summary.report_date}
          </p>
        )}
      </div>
    </section>
  );
}
