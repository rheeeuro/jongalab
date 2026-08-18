import type { Metadata } from "next";
import { FlaskConical, HelpCircle } from "lucide-react";
import { getEdgeRules, getEdgeRuleDaily } from "@/lib/api";
import type { EdgeRuleWithDaily } from "@/types";
import { EdgeBoard } from "@/components/EdgeBoard";

export const metadata: Metadata = {
  title: "전략 실험실 - 종가베팅 전략 검증",
  description:
    "종가베팅 종목을 고를 때 쓰는 전략이 실제 시장에서 통했는지 검사한 성적이에요. 전략마다 성공률과 평균 수익, 지금 어디까지 검사했는지를 공개해요.",
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
            매매 아이디어를 실제 시장에서 통하는지 시험해 보고, 성적이 좋은 전략만 종목 고를 때 써요.
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
              여기 있는 <b>전략</b> 하나하나는 &ldquo;이런 조건에 맞는 종목을 오늘 사면 내일 아침에
              오른다&rdquo;라는 아이디어예요. <b>거래일마다 아침</b>에, 전날 후보였던 종목 전체에 각
              전략의 조건을 대 보고 &ldquo;정말 올랐는지&rdquo; 자동으로 점수를 매겨 쌓아요.
            </p>
            <p>
              <b>검증 중</b>(회색)은 아직 실제로 쓰지 않고 성적만 매겨보는 단계예요.{" "}
              <b className="text-emerald-600 dark:text-emerald-400">적용 중</b>(초록)만 종목을 고를 때
              실제로 써요. 카드 아래 막대는 <b>서로 다른 날 10일</b>이 모였는지만 보여줘요 — 같은 날
              뽑힌 종목들은 장이 좋으면 다 같이 오르니까, 종목이 아무리 많아도 날이 적으면 운인지
              실력인지 가릴 수 없거든요. <b>막대가 꽉 차도 바로 합격은 아니에요.</b> 10일을 채운
              다음에는 한 번에 평균해서 이익이 났는지, 같은 날 다른 후보들보다 나았는지도 같이 봐요.
              아직 못 채운 게 있으면 막대 아래에 <b>&ldquo;남은 조건&rdquo;</b>으로 적어 둬요. 전부
              채우면{" "}
              <b className="text-rose-600 dark:text-rose-400">검증 통과</b> 딱지가 붙고, 관리자가 한 번 더
              확인한 뒤에 실제로 써요.
            </p>
            <p>
              카드의 <b>평균 수익</b>은 세금·수수료를 뺀 뒤 한 번에 평균 몇 % 벌었는지예요.{" "}
              <b>보수적 수익</b>은 운이 나빴을 경우까지 감안해 낮춰 잡은 값이고, 이 값이 0%보다 커야
              합격이에요. 카드를 누르면 날짜별 성적과 종목을 고르는 조건, 최근에 조건에 걸린 종목을
              볼 수 있어요.
            </p>
            <p className="text-slate-400 dark:text-slate-500">
              전략을 쓰거나 그만두는 건 관리자만 정할 수 있어요. 이 화면은 누구나 볼 수 있지만
              바꿀 수는 없어요.
            </p>
          </div>
        </details>

        <EdgeBoard rules={withDaily} />
      </div>
    </main>
  );
}
