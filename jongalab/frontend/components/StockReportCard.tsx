import Link from "next/link";
import { Crown, FlaskConical } from "lucide-react";
import { StockReport } from "@/types";
import { CARD, CARD_HOVER } from "@/lib/ui";

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white dark:bg-slate-600",
  D: "bg-slate-300 text-white dark:bg-slate-700",
};

/** 카드 좌측 세로 띠 — 수급 등급을 배지와 **같은 색**으로 한 번 더 낸다.
 *  10장이 세로로 쌓일 때 카드끼리 구분되는 유일한 단서였고(전부 흰 카드였다),
 *  색 단독 표시가 아니라 같은 카드 안의 `수급 A` 배지가 라벨을 겸한다. */
const GRADE_BAR: Record<string, string> = {
  S: "bg-rose-500",
  A: "bg-orange-500",
  B: "bg-amber-500",
  C: "bg-slate-300 dark:bg-slate-600",
  D: "bg-slate-200 dark:bg-slate-700",
};

type GapLine = { label: "NXT" | "KRX"; pct: number };

function resolveGapLines(r: StockReport): GapLine[] {
  // 텔레그램 포맷과 동일: NXT+KRX 둘 다 있으면 KRX는 NXT→KRX 장중 델타
  const hasNxt = typeof r.gap_nxt_pct === "number";
  const hasKrx = typeof r.gap_krx_pct === "number";
  const lines: GapLine[] = [];
  if (hasNxt) lines.push({ label: "NXT", pct: r.gap_nxt_pct! });
  if (hasKrx) {
    if (
      hasNxt &&
      r.gap_nxt_price != null &&
      r.gap_krx_price != null &&
      r.gap_nxt_price > 0
    ) {
      lines.push({
        label: "KRX",
        pct: ((r.gap_krx_price - r.gap_nxt_price) / r.gap_nxt_price) * 100,
      });
    } else {
      lines.push({ label: "KRX", pct: r.gap_krx_pct! });
    }
  }
  return lines;
}

export function finalGapPct(r: StockReport): number | null {
  // 리포트가 → 최종(KRX 우선, NXT 폴백) 누적 등락 기준
  if (typeof r.gap_krx_pct === "number") return r.gap_krx_pct;
  if (typeof r.gap_nxt_pct === "number") return r.gap_nxt_pct;
  return null;
}

function pctColor(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-500";
}

/** 추천 픽 카드 — 홈(오늘의 추천)과 리포트 상세가 공유한다.
 *
 * **표시 순번(1,2,3…)을 매기지 않는다.** hybrid/rules 모드에서 뽑힌 종목은 점수 순위와
 * 무관해(실측 2026-08-07 rank_no = 2·4·7…53, 1위가 없다) 목록 순번을 매기면 점수로 뽑힌
 * 것처럼 읽힌다. 순위 대신 **점수 배지 + '왜 뽑혔나'(룰 한글 제목)** 로 선정 근거를 직접 낸다.
 * 점수 순위(rank_no)가 필요하면 리포트 상세에서 본다.
 *
 * @param ruleTitles 부모가 `lib/api.getRuleTitleMap()` 으로 미리 매핑한 한글 제목.
 *   슬러그(f5_prog_persistent)를 화면에 노출하지 않기 위한 값이며, 비어 있으면 근거 줄을
 *   '점수 상위 선정'으로 낸다(rule_names 가 NULL = 점수순 선정).
 */
export function StockReportCard({
  report: r,
  date,
  ruleTitles = [],
  featured = false,
}: {
  report: StockReport;
  date: string;
  ruleTitles?: string[];
  /** 그날 규칙이 가장 많이 겹친 종목 — 목록 맨 앞에서 한 줄을 통째로 쓴다.
   *  배지에는 **기준만** 적는다('유력'·'강력 추천' 같은 예측 문구 금지). */
  featured?: boolean;
}) {
  const isUp = r.change_pct > 0;
  const isDown = r.change_pct < 0;
  const isRulePick = Boolean(r.rule_names);
  const gapLines = resolveGapLines(r);
  const totalPct = finalGapPct(r);
  // 결과가 나온 카드는 배경을 옅게 물들인다. 결과 전(당일 저녁)엔 기본 표면이라
  // 카드 구분은 좌측 등급 띠와 헤어라인 링이 맡는다.
  const gapTone =
    totalPct === null || totalPct === 0
      ? CARD
      : totalPct > 0
        ? "rounded-2xl bg-rose-50/60 shadow-sm ring-1 ring-rose-200/60 dark:bg-rose-950/20 dark:shadow-none dark:ring-rose-900/40"
        : "rounded-2xl bg-blue-50/60 shadow-sm ring-1 ring-blue-200/60 dark:bg-blue-950/20 dark:shadow-none dark:ring-blue-900/40";

  // 근거는 한 줄에 최대 2개까지만 — 나머지는 '외 N' 으로 접어 카드 높이를 고정한다.
  const shownRules = ruleTitles.slice(0, 2);
  const hiddenRuleCount = ruleTitles.length - shownRules.length;
  const reasonText =
    isRulePick && shownRules.length > 0
      ? shownRules.join(" · ") +
        (hiddenRuleCount > 0 ? ` 외 ${hiddenRuleCount}` : "")
      : isRulePick
        ? "검증된 규칙 선정"
        : "종합 점수 상위 선정";

  return (
    <Link
      href={`/reports/${date}/${r.stock_code}`}
      className={`group relative flex flex-col overflow-hidden p-4 pl-5 ${gapTone} ${CARD_HOVER} ${
        featured
          ? "ring-2 ring-indigo-300 @4xl:col-span-3 dark:ring-indigo-500/40"
          : ""
      }`}
    >
      <span
        aria-hidden
        className={`absolute inset-y-0 left-0 w-1.5 ${GRADE_BAR[r.supply_grade] || GRADE_BAR.D}`}
      />

      {featured && (
        <p className="mb-2 inline-flex w-fit items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-extrabold text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
          <FlaskConical className="h-3 w-3" />
          규칙 {ruleTitles.length}개가 겹쳐 고른 종목
        </p>
      )}

      {/* 상단: 종목명 + 플래그 / 우측: 현재가 + 등락율 */}
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span
              className={`min-w-0 truncate font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-400 ${
                featured ? "text-lg" : ""
              }`}
            >
              {r.stock_name}
            </span>
            {r.is_leader && (
              <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
            )}
            {r.is_theme_stock && (
              <span className="shrink-0 rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] font-extrabold text-orange-600 dark:bg-orange-950/40 dark:text-orange-400">
                테마
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">
            {r.sector || "기타"} ·{" "}
            {(r.trading_value / 1e8).toLocaleString("ko-KR", {
              maximumFractionDigits: 0,
            })}
            억
          </p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <div className="text-sm font-extrabold text-slate-900 dark:text-slate-100">
            {r.current_price.toLocaleString("ko-KR")}
            <span className="ml-0.5 text-[10px] font-bold text-slate-400">
              원
            </span>
          </div>
          {/* 당일 등락률 — 카드마다 값이 다른 유일한 큰 색면이라 카드 구분의 1차 단서다 */}
          <div
            className={`mt-1 inline-block rounded-md px-1.5 py-0.5 text-xs font-extrabold ${
              isUp
                ? "bg-rose-100/80 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
                : isDown
                  ? "bg-blue-100/80 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300"
                  : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            }`}
          >
            {isUp ? "+" : ""}
            {r.change_pct.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* 왜 뽑혔나 + 점수 — 한 줄. 예전엔 라벨 붙은 박스 + 점수 줄이 따로였는데,
          홈에서 카드 10장이 세로로 쌓이면 그만큼 시장 지표가 화면 밖으로 밀렸다.
          플라스크 아이콘이 '선정 근거'를 대신 표시하고, 전체 규칙은 title 에 남긴다. */}
      <div className="mt-2.5 flex items-center gap-1.5">
        <FlaskConical className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
        <p
          title={ruleTitles.length > 0 ? ruleTitles.join(", ") : undefined}
          className="min-w-0 flex-1 truncate text-xs font-bold text-slate-700 dark:text-slate-200"
        >
          {reasonText}
        </p>
        <span className="shrink-0 rounded-lg bg-indigo-50 px-1.5 py-0.5 tabular-nums dark:bg-indigo-950/50">
          <span className="text-sm font-extrabold text-indigo-700 dark:text-indigo-300">
            {r.score.toFixed(0)}
          </span>
          <span className="text-[10px] font-bold text-indigo-400 dark:text-indigo-400/70">
            점
          </span>
        </span>
      </div>

      {/* 배지 + 다음날 아침 갭 결과(NXT·KRX·최종) — 한 줄에 묶는다 */}
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-bold">
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
            GRADE_TONE[r.supply_grade] || GRADE_TONE.D
          }`}
        >
          수급 {r.supply_grade}
        </span>
        {(r.news_count ?? 0) > 0 && (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
            뉴스 {r.news_count}
          </span>
        )}
        {/* 무상증자 권리락일(sql/50) — 아래 등락률이 조정 기준가 대비임을 밝힌다.
            (없으면 배정비율만큼 낮아진 기준가 때문에 오른 종목이 하락으로 읽힌다) */}
        {r.gap_ex_rights_ratio != null && (
          <span
            title="무상증자 권리락일입니다 — 배정비율만큼 낮아진 권리락 기준가 대비 등락률입니다"
            className="shrink-0 rounded-full bg-amber-200/80 px-1.5 py-0.5 text-[10px] font-extrabold text-amber-900 dark:bg-amber-900/50 dark:text-amber-200"
          >
            권리락
          </span>
        )}

        {(gapLines.length > 0 || totalPct !== null) && (
          <span className="ml-auto flex shrink-0 items-baseline gap-2">
            {gapLines.map((g) => (
              <span key={g.label} className="inline-flex items-baseline gap-0.5">
                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                  {g.label}
                </span>
                <span className={`tabular-nums ${pctColor(g.pct)}`}>
                  {g.pct > 0 ? "+" : ""}
                  {g.pct.toFixed(2)}%
                </span>
              </span>
            ))}
            {totalPct !== null && (
              <span className="inline-flex items-baseline gap-0.5">
                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                  최종
                </span>
                <span className={`font-extrabold tabular-nums ${pctColor(totalPct)}`}>
                  {totalPct > 0 ? "+" : ""}
                  {totalPct.toFixed(2)}%
                </span>
              </span>
            )}
          </span>
        )}
      </div>
    </Link>
  );
}
