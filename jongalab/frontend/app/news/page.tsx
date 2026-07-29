import type { Metadata } from "next";
import Link from "next/link";
import { Newspaper } from "lucide-react";
import { NewsHeatItem, NewsMaterialRow } from "@/types";
import { MaterialBadge, materialAxisLabels } from "@/components/MaterialBadge";
import { NewsHeat } from "@/components/today/NewsHeat";
import { apiFetch } from "@/lib/api";

export const metadata: Metadata = {
  title: "뉴스 재료",
  description: "오늘 유니버스 종목의 뉴스 재료와 지속성 판정",
};

export const dynamic = "force-dynamic";

async function getMaterials(): Promise<NewsMaterialRow[]> {
  const res = await apiFetch<{ success: boolean; data: NewsMaterialRow[] } | null>(
    `/api/news/materials`,
    null,
  );
  return res?.data ?? [];
}

async function getHeat(): Promise<NewsHeatItem[]> {
  const res = await apiFetch<{ success: boolean; data: NewsHeatItem[] } | null>(
    `/api/news/heat?hours=24&limit=12`,
    null,
  );
  return res?.data ?? [];
}

function todayStr(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

/** 재료 카드 한 장 — 등급·유형·요약·4축. 클릭하면 판정 근거가 있는 리포트 상세로. */
function MaterialCard({ row, date }: { row: NewsMaterialRow; date: string }) {
  const chg = row.change_pct ?? 0;
  const axes = materialAxisLabels(row);
  return (
    <Link
      href={`/reports/${date}/${row.stock_code}`}
      className="block rounded-2xl bg-white p-4 transition-colors hover:bg-slate-50 dark:bg-slate-900/60 dark:hover:bg-slate-800/60"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
            {row.stock_name}
          </span>
          <MaterialBadge durability={row.news_durability} />
          {row.news_catalyst && (
            <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {row.news_catalyst}
            </span>
          )}
          {row.selected === 1 && (
            <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
              선정
            </span>
          )}
        </div>
        <span
          className={`shrink-0 text-sm font-extrabold tabular-nums ${
            chg > 0
              ? "text-red-500 dark:text-red-400"
              : chg < 0
                ? "text-blue-500 dark:text-blue-400"
                : "text-slate-400"
          }`}
        >
          {chg > 0 ? "+" : ""}
          {chg.toFixed(1)}%
        </span>
      </div>

      {row.news_summary && (
        <p className="mt-2 line-clamp-2 break-words text-xs leading-relaxed text-slate-600 dark:text-slate-300">
          {row.news_summary}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] font-medium text-slate-400 dark:text-slate-500">
        <span className="tabular-nums">뉴스 {row.news_count}건</span>
        {axes.map((t) => (
          <span key={t}>· {t}</span>
        ))}
      </div>
    </Link>
  );
}

function Group({
  title,
  hint,
  rows,
  date,
}: {
  title: string;
  hint: string;
  rows: NewsMaterialRow[];
  date: string;
}) {
  if (!rows.length) return null;
  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-2">
        <h2 className="text-base font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-lg">
          {title}
          <span className="ml-1.5 text-xs font-bold text-slate-400">{rows.length}</span>
        </h2>
        <span className="shrink-0 text-[11px] font-medium text-slate-400">{hint}</span>
      </div>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {rows.map((r) => (
          <MaterialCard key={r.stock_code} row={r} date={date} />
        ))}
      </div>
    </section>
  );
}

/**
 * 뉴스 재료 탭 — 오늘 유니버스 종목의 재료를 **지속성 등급으로 묶어** 보여준다.
 *
 * 의도적으로 **속보 피드(전 종목 헤드라인 스트림)는 두지 않았다** — 하루 400~650건이 흐르는
 * 파이어호스는 읽히지 않고, 이 화면의 축은 '오늘 어떤 재료가 떴고 그게 이어질 성질인가'다.
 * 개별 헤드라인은 종목 상세(오늘의 뉴스)에서 시세 기사와 분리해 본다.
 *
 * ⚠️ 지속성 라벨은 candidate rule 표본(관찰 전용·미검증)이다. 화면 상단에 그 사실을 적어
 * 매수 신호로 읽히지 않게 한다.
 *
 * 모바일 우선: 세로 카드 리스트, lg 부터 2열.
 */
export default async function NewsPage() {
  const [rows, heat] = await Promise.all([getMaterials(), getHeat()]);
  const date = todayStr();

  const durable = rows.filter((r) => r.news_durability === "연속");
  const spent = rows.filter((r) => r.news_durability === "소진");
  const rest = rows.filter(
    (r) => r.news_durability !== "연속" && r.news_durability !== "소진",
  );

  return (
    <main className="mx-auto max-w-7xl space-y-8 px-4 py-6 pb-24 sm:px-6 lg:pb-10">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
          <Newspaper className="h-6 w-6 text-emerald-500" />
          뉴스 재료
        </h1>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          오늘 유니버스에서 뉴스가 있는 {rows.length}종목의 재료를 AI가 읽고 <b>이어질 성질인지</b>{" "}
          판정한 결과입니다. 다음 예정 사건이 남고 수치가 확정되지 않았으면 &lsquo;연속&rsquo;,
          수치가 확정되고 남은 일정이 없으면 &lsquo;소진&rsquo;입니다.
          <br />
          <span className="font-bold text-slate-400 dark:text-slate-500">
            ⚠️ 관찰 중 · 미검증 — 매수 신호가 아니고 실매매에 개입하지 않습니다(성적만 기록 중).
          </span>
        </p>
      </header>

      {rows.length === 0 && (
        <p className="rounded-2xl bg-white p-6 text-center text-sm font-medium text-slate-400 dark:bg-slate-900/60">
          오늘 뉴스가 매칭된 유니버스 종목이 아직 없습니다.
        </p>
      )}

      <Group
        title="이어지는 재료"
        hint="다음 일정 남음 · 수치 미확정"
        rows={durable}
        date={date}
      />
      <Group title="소진된 재료" hint="수치 확정 · 남은 일정 없음" rows={spent} date={date} />
      <Group title="판정 보류·중립" hint="재료 특정 불가 또는 갈림" rows={rest} date={date} />

      <NewsHeat items={heat} showAllLink={false} />
    </main>
  );
}
