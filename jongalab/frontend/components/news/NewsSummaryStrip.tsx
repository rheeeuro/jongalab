import { NewsMaterialRow } from "@/types";

/**
 * 뉴스 탭 상단 요약 — "오늘 뉴스판이 어떤 하루였나"를 카드 **한 장**으로 먼저 준다.
 *
 * 첫 화면에서 규모를 먼저 준다(스크롤해야 규모를 아는 화면은 뉴스 탭으로 쓸모가 없다).
 * 값은 전부 **이 화면이 이미 받은 데이터에서 정확히 세는 것만** 쓴다 — 상한이 걸린 목록
 * (heat 는 limit 로 잘린다)에서 센 수를 전체 수인 양 보여주지 않는다.
 *
 * 기사 수는 **헤드라인 스트림이 나열하는 수와 같은 수**다(시세 기사 제외분은 보조줄에
 * 따로 밝힌다). 요약이 도달할 수 없는 총계를 말하면 아래 스트림 헤더와 어긋난다.
 *
 * 재료 유형은 '기타'를 세지 않는다 — 라벨 분포상 '기타'가 최다인 날이 흔해서, 세면
 * "많이 나온 유형: 기타"만 나오고 정보가 0이 된다.
 *
 * 모바일 우선: 카드 1장 안에 2열 그리드, sm 부터 4열 한 줄.
 */
export function NewsSummaryStrip({
  rows,
  articleCount,
  priceCount = 0,
}: {
  rows: NewsMaterialRow[];
  /** 스트림이 나열하는 기사 수 (시세 기사 제외 기준) */
  articleCount: number;
  /** 그 중 숨긴 시세 기사 수 */
  priceCount?: number;
}) {
  const durable = rows.filter((r) => r.news_durability === "연속").length;
  const up = rows.filter((r) => (r.change_pct ?? 0) > 0).length;
  const down = rows.filter((r) => (r.change_pct ?? 0) < 0).length;

  const catalystCounts = new Map<string, number>();
  for (const r of rows) {
    const c = r.news_catalyst;
    if (c && c !== "기타") catalystCounts.set(c, (catalystCounts.get(c) ?? 0) + 1);
  }
  const topCatalyst = [...catalystCounts.entries()].sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="rounded-2xl bg-white p-4 dark:bg-slate-900/60">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Stat
          label="재료가 붙은 후보"
          value={rows.length}
          unit="종목"
          sub={rows.length ? `상승 ${up} · 하락 ${down}` : "없음"}
        />
        <Stat
          label="모아 온 기사"
          value={articleCount}
          unit="건"
          sub={priceCount ? `시세 기사 ${priceCount}건 제외` : undefined}
        />
        <Stat
          label="이어지는 재료"
          value={durable}
          unit="종목"
          sub={durable ? "다음 일정 남음" : undefined}
        />
        <Stat
          label="많이 나온 유형"
          text={topCatalyst ? topCatalyst[0] : "—"}
          sub={topCatalyst ? `${topCatalyst[1]}종목` : undefined}
        />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  text,
  sub,
}: {
  label: string;
  value?: number;
  unit?: string;
  text?: string;
  sub?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-bold text-slate-400 dark:text-slate-500">{label}</p>
      <p className="mt-0.5 truncate text-xl font-extrabold tracking-tight text-slate-900 tabular-nums dark:text-slate-100">
        {text ?? value}
        {unit && <span className="ml-0.5 text-xs font-bold text-slate-400">{unit}</span>}
      </p>
      <p className="mt-0.5 truncate text-[11px] font-medium text-slate-400 dark:text-slate-500">
        {sub ?? " "}
      </p>
    </div>
  );
}
