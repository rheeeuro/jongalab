import { NewsMaterialRow } from "@/types";

/**
 * 뉴스 탭 상단 요약 타일 — "오늘 뉴스판이 어떤 하루였나"를 4개 숫자로 먼저 준다.
 *
 * 예전 화면은 첫 화면이 면책 문구 4줄 + 카드 그리드라, 스크롤하기 전에는 규모조차 알 수 없었다.
 * 타일 값은 전부 **이 화면이 이미 받은 데이터에서 정확히 세는 것만** 쓴다 — 상한이 걸린 목록
 * (heat 는 limit 로 잘린다)에서 센 수를 전체 수인 양 보여주지 않는다.
 *
 * 모바일 우선: 2열 그리드, sm 부터 4열.
 */
export function NewsSummaryStrip({
  rows,
  articleCount,
}: {
  rows: NewsMaterialRow[];
  /** 그 날 수집된 기사 수 (스트림 total — 종목 중복을 접은 값) */
  articleCount: number;
}) {
  const durable = rows.filter((r) => r.news_durability === "연속").length;
  const up = rows.filter((r) => (r.change_pct ?? 0) > 0).length;
  const down = rows.filter((r) => (r.change_pct ?? 0) < 0).length;

  const catalystCounts = new Map<string, number>();
  for (const r of rows) {
    const c = r.news_catalyst;
    if (c) catalystCounts.set(c, (catalystCounts.get(c) ?? 0) + 1);
  }
  const topCatalyst = [...catalystCounts.entries()].sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile label="수집 기사" value={articleCount} unit="건" />
      <Tile
        label="재료 종목"
        value={rows.length}
        unit="종목"
        sub={rows.length ? `상승 ${up} · 하락 ${down}` : undefined}
      />
      <Tile
        label="이어지는 재료"
        value={durable}
        unit="종목"
        sub={rows.length ? "다음 일정 남음" : undefined}
      />
      <Tile
        label="최다 재료 유형"
        text={topCatalyst ? topCatalyst[0] : "—"}
        sub={topCatalyst ? `${topCatalyst[1]}종목` : undefined}
      />
    </div>
  );
}

function Tile({
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
    <div className="rounded-2xl bg-white p-3 dark:bg-slate-900/60">
      <p className="text-[11px] font-bold text-slate-400 dark:text-slate-500">{label}</p>
      <p className="mt-0.5 truncate text-xl font-extrabold tracking-tight text-slate-900 tabular-nums dark:text-slate-100">
        {text ?? value}
        {unit && (
          <span className="ml-0.5 text-xs font-bold text-slate-400">{unit}</span>
        )}
      </p>
      <p className="mt-0.5 h-4 truncate text-[11px] font-medium text-slate-400 dark:text-slate-500">
        {sub ?? ""}
      </p>
    </div>
  );
}
