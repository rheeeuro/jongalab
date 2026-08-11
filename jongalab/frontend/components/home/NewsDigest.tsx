import Link from "next/link";
import { ChevronRight, Newspaper } from "lucide-react";
import { NewsHeatItem } from "@/types";
import { CARD, INSET } from "@/lib/ui";
import { newsHeatLabel } from "@/lib/news";

/** 뉴스가 몰린 종목 — 홈의 **압축본**이다(전체는 `/news`).
 *
 * 세로 목록인 이유: 데스크탑에서는 우측 사이드바(≈19rem) 안에 들어가고 모바일에서는
 * 픽 목록 아래에 오는데, 가로 스크롤 칩은 좁은 사이드바에서 읽히지 않는다.
 *
 * 막대는 **자기 기저 대비 배수**(`surprise`)의 크기이고, 목록 안 최댓값을 100%로 잡는다.
 * 색은 **브랜드 보라 한 가지**다 — 이건 손익이 아니라 화제성이라 빨강/파랑(등락)을 쓰면 안 된다.
 * 로고색(#5f219c)에 가장 가까우면서 하락(파랑)과 색맹 조건에서도 갈리는 스텝을 골랐다
 * (light `purple-800` ΔE 12.3 deutan / dark `purple-300` ΔE 18.3 protan vs 파랑). 밝은 보라
 * (purple-500/600)는 파랑과 ΔE 1~3 이라 쓰지 않는다. 숫자 라벨을 항상 함께 내서 색 없이도 읽힌다.
 */
export function NewsDigest({
  items,
  date,
}: {
  items: NewsHeatItem[];
  date: string;
}) {
  const top = items.slice(0, 5);
  if (!top.length) return null;

  const max = Math.max(...top.map((n) => n.surprise ?? 1), 1);

  return (
    <section className={`p-4 ${CARD}`}>
      <div className="flex items-center gap-1.5">
        <Newspaper className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
        <h2 className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
          뉴스가 몰린 종목
        </h2>
        <Link
          href={`/news?date=${date}`}
          className="ml-auto inline-flex shrink-0 items-center gap-0.5 text-[11px] font-bold text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
        >
          뉴스
          <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
      {/* 창(24시간)과 막대 기준을 못 박는다 — 뉴스 탭 랭킹은 '하루' 창이라 값이 달라 보인다. */}
      <p className="mt-0.5 text-[10px] font-medium text-slate-400 dark:text-slate-500">
        최근 24시간 · 평소 대비 뉴스량
      </p>

      <ul className="mt-2 space-y-2.5">
        {top.map((n) => {
          const surprise = n.surprise ?? 1;
          const label = newsHeatLabel(n.mention_count, n.prior_avg);
          return (
            <li key={n.ticker}>
              <Link
                href={`/stocks/${n.ticker}`}
                className="group block transition-colors hover:text-purple-800 dark:hover:text-purple-300"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <p className="flex min-w-0 items-center gap-1 text-sm font-extrabold text-slate-900 dark:text-slate-100">
                    <span className="truncate">
                      {n.company_name || n.ticker}
                    </span>
                    {n.in_universe === 1 && (
                      <span className="shrink-0 rounded-full bg-indigo-100 px-1 text-[10px] font-extrabold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                        후보
                      </span>
                    )}
                  </p>
                  <p
                    className={`shrink-0 text-[11px] font-extrabold tabular-nums ${
                      label.emphasis
                        ? "text-slate-600 dark:text-slate-300"
                        : "text-slate-400 dark:text-slate-500"
                    }`}
                  >
                    {label.headline}
                  </p>
                </div>
                <div className={`mt-1 h-1.5 ${INSET}`}>
                  <div
                    className="h-full rounded-lg bg-purple-800 dark:bg-purple-300"
                    style={{ width: `${Math.max((surprise / max) * 100, 4)}%` }}
                  />
                </div>
                <p className="mt-0.5 truncate text-[10px] font-medium text-slate-400 tabular-nums dark:text-slate-500">
                  {label.detail}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
