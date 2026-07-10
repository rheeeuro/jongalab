import type { Metadata } from "next";
import { FlaskConical, HelpCircle } from "lucide-react";
import { getEdgeRules, getEdgeRuleDaily } from "@/lib/api";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeBoard } from "@/components/EdgeBoard";

export const metadata: Metadata = {
  title: "전략 실험실",
  alternates: { canonical: "/lab" },
};

export const dynamic = "force-dynamic";

export default async function EdgePage() {
  const rules = await getEdgeRules();
  // 각 rule 의 일별 시계열(스칼라만) + 최신 매칭 1일치를 병렬로 실어 내려준다(rule 수가 적음).
  const daily = await Promise.all(rules.map((r) => getEdgeRuleDaily(r.id)));
  const withDaily: EdgeRuleWithDaily[] = rules.map((r, i) => ({
    ...r,
    daily: daily[i].daily,
    latest_matched: daily[i].latest_matched,
  }));

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-10">
        <header className="space-y-1">
          <h1 className="flex items-center gap-2 text-xl font-extrabold text-slate-900 sm:text-2xl dark:text-slate-100">
            <FlaskConical className="h-5 w-5 text-rose-500" />
            전략 실험실
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            매매 아이디어를 실제 시장 데이터로 검증하고, 검증을 통과한 전략만 종목 선정에 씁니다.
          </p>
        </header>

        {/* 처음 보는 사람용 도움말 — 접이식(모바일에서 본문을 가리지 않게) */}
        <details className="rounded-2xl border border-indigo-100 bg-indigo-50/50 px-4 py-3 dark:border-indigo-500/20 dark:bg-indigo-500/5">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
            <HelpCircle className="h-4 w-4 shrink-0" />
            이 화면은 어떻게 보나요?
          </summary>
          <div className="mt-3 space-y-2.5 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
            <p>
              여기 있는 <b>전략</b> 하나하나는 &ldquo;이런 조건의 종목을 오늘 사면 내일 아침 수익이
              난다&rdquo;라는 매매 아이디어입니다. 시스템이 <b>매 거래일 아침</b>, 전날 후보 종목 전체에
              각 전략의 조건을 적용해 &ldquo;정말 수익이 났는지&rdquo;를 자동으로 채점해 쌓습니다.
            </p>
            <p>
              <b>검증 중</b>(회색)은 모의 채점만 하는 단계입니다.{" "}
              <b className="text-emerald-600 dark:text-emerald-400">적용 중</b>(초록)만 종목 선정에
              반영됩니다. 검증 중 전략이 충분한 횟수(40회 이상)를 쌓고 성적이 우연이라 보기 어려운
              수준이 되면 <b className="text-rose-600 dark:text-rose-400">검증 통과</b> 배지가 붙고,
              관리자가 확인 후 적용합니다.
            </p>
            <p>
              카드의 <b>평균 수익</b>은 세금·수수료를 뺀 회당 평균 수익률이고, <b>보수적 수익</b>은
              운이 나쁜 경우까지 감안한 하한 추정입니다(0%보다 커야 통과). 카드를 누르면 날짜별
              성적, 종목 선정 조건, 최근에 조건에 걸린 종목을 볼 수 있습니다.
            </p>
            <p className="text-slate-400 dark:text-slate-500">
              전략의 적용·종료는 관리자 페이지(전략 관리)에서만 가능합니다. 이 화면은 누구나
              볼 수 있지만 바꿀 수는 없습니다.
            </p>
          </div>
        </details>

        <EdgeBoard rules={withDaily} />
      </div>
    </main>
  );
}
