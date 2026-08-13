import Link from "next/link";
import { Crown, FlaskConical, Newspaper } from "lucide-react";
import { EdgeRule, StockReport } from "@/types";
import { newsHeatLabel } from "@/lib/news";
import { CARD, CARD_HOVER, HERO_ROW_H, INSET } from "@/lib/ui";

/** 1등 카드 근거 블록에 칩으로 낼 규칙 수 — **규칙 줄이 항상 1줄이 되도록** 정한다.
 *  실측 규칙 수는 1~4개이고 이름 칩 3개까지가 한 줄에 들어간다. 넘는 만큼은 '외 N개'로
 *  접어, 규칙 수와 무관하게 카드 높이를 `HERO_ROW_H` 하한 안에 고정한다. */
const RULE_CHIPS = 3;

const GRADE_TONE: Record<string, string> = {
  S: "bg-rose-500 text-white",
  A: "bg-orange-500 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-slate-400 text-white dark:bg-slate-600",
  D: "bg-slate-300 text-white dark:bg-slate-700",
};

/** 카드 좌측 세로 띠 — **당일 등락 방향**을 옅은 색으로 낸다(상승 빨강 / 하락 파랑).
 *  10장이 세로로 쌓일 때 카드끼리 구분되는 단서이며, 색 단독 표시가 아니라 같은 카드 안의
 *  등락률 배지(+2.3% / -1.1%)가 부호로 라벨을 겸한다. 옅게 두는 이유는 카드 배경(갭 결과)과
 *  등락률 배지가 이미 같은 적/청 계열이라, 띠까지 진하면 색이 서로 경쟁하기 때문. */
function changeBar(pct: number): string {
  if (pct > 0) return "bg-rose-200 dark:bg-rose-500/25";
  if (pct < 0) return "bg-blue-200 dark:bg-blue-500/25";
  return "bg-slate-200 dark:bg-slate-700/60";
}

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

/** 리포트가 → 누적 등락(KRX 우선, NXT 폴백). 카드에 숫자로 찍지는 않고
 *  카드 배경 톤과 목록 하단 '이 날 결과' 평균의 기준값으로만 쓴다. */
export function finalGapPct(r: StockReport): number | null {
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
 * 무관해(실측 rank_no 가 2·4·7…53 처럼 흩어지고 1위가 없는 날이 있다) 순번을 매기면 점수로 뽑힌
 * 것처럼 읽힌다. 순위 대신 **점수 배지 + '왜 뽑혔나'(룰 한글 제목)** 로 선정 근거를 직접 낸다.
 * 점수 순위(rank_no)가 필요하면 리포트 상세에서 본다.
 *
 * **1등 카드는 데스크탑에서만 아래에 '선정 근거' 블록이 붙는다**(아래 `featured` 참고).
 *
 * @param rules 이 종목을 뽑은 룰 원본(`lib/api.getRuleMap`). 쓰는 건 한글 제목뿐이고
 *   (1등 카드는 그 제목을 칩으로 낸다), 비어 있으면 근거 줄을 '점수 상위 선정'으로 낸다
 *   (rule_names 가 NULL = 점수순 선정).
 */
export function StockReportCard({
  report: r,
  date,
  rules = [],
  featured = false,
}: {
  report: StockReport;
  date: string;
  rules?: EdgeRule[];
  /** 그날 규칙이 가장 많이 겹친 종목 — 목록 맨 앞에서 한 줄을 통째로 쓴다(`col-span-full`).
   *  높이는 홈 사이드바의 성적 카드와 같은 `HERO_ROW_H` 하한을 쓴다(둘이 어긋나면 우측
   *  뉴스 카드 상단이 좌측 2·3·4등 줄과 틀어진다).
   *  배지에는 **기준만** 적는다('유력'·'강력 추천' 같은 예측 문구 금지). */
  featured?: boolean;
}) {
  const ruleTitles = rules.map((rule) => rule.title || rule.name);
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

  /** 1등 카드는 **종목명만** 키운다(데스크탑 36px). 가격·점수·배지까지 같이 키우면 카드가
   *  통째로 확대된 것처럼 보인다 — 나머지는 일반 카드와 같은 크기이고,
   *  카드가 1등임은 종목명 크기·전체 폭·인디고 링·아래 근거 블록이 이미 말한다. */
  const nameSize = featured ? "text-lg lg:text-4xl" : "";

  /** 1등 카드는 안쪽 여백을 한 단 넓게 쓴다 — 카드 폭이 한 줄을 통째로 쓰는데 여백이 일반
   *  카드와 같으면 내용이 테두리에 붙어 보인다. 좌측은 등락 띠(w-1.5) 위를 지나므로 한 단 더 준다.
   *
   *  ⚠️ **가로(`px`)만 늘린다.** 세로 여백을 늘리면 카드가 그만큼 커지고, `HERO_ROW_H` 하한을
   *  넘기는 순간 우측 성적 카드와 상단 정렬이 깨진다(2026-08-11 `lg:p-6` 로 256px 이 되어 실패). */
  const padding = featured ? "px-5 py-4 pl-6 lg:px-6 lg:pl-7" : "p-4 pl-5";

  /** 1등 카드 근거 블록의 뉴스 줄 라벨. 뉴스가 없는 날은 null — 줄은 그대로 두고
   *  '당일 뉴스 없음' 플레이스홀더로 바뀐다(헤드라인 '뉴스 없음' + 근거 '뉴스 0건'은
   *  같은 말을 두 번 하는 꼴이라 라벨을 그대로 쓰지 않는다). */
  const newsHeat =
    (r.news_count ?? 0) > 0
      ? newsHeatLabel(r.news_count, r.news_prior_avg)
      : null;

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
      className={`group relative flex flex-col overflow-hidden ${padding} ${gapTone} ${CARD_HOVER} ${
        featured
          ? `ring-2 ring-indigo-300 col-span-full lg:justify-between ${HERO_ROW_H} dark:ring-indigo-500/40`
          : ""
      }`}
    >
      <span
        aria-hidden
        className={`absolute inset-y-0 left-0 w-1.5 ${changeBar(r.change_pct)}`}
      />

      {/* 데스크탑 1등 카드는 아래 근거 블록이 규칙을 이름으로 부르므로 이 배지를 반복하지 않는다. */}
      {featured && (
        <p className="mb-2 inline-flex w-fit items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-extrabold text-indigo-700 lg:hidden dark:bg-indigo-950/50 dark:text-indigo-300">
          <FlaskConical className="h-3 w-3" />
          규칙 {ruleTitles.length}개가 겹쳐 고른 종목
        </p>
      )}

      {/* 상단: 종목명 + 플래그 / 우측: 현재가 + 등락율 */}
      <div className="flex items-start gap-2">
        {/* 종목명·섹터 열은 우측 숫자 열(가격·등락률·점수)보다 짧아 위로 붙어 보인다 →
            `self-center` 로 숫자 열 높이에 세로 중앙을 맞춘다. 짧은 쪽만 옮기는 것이라
            행 높이(=카드 높이)는 그대로다. */}
        <div className="min-w-0 flex-1 self-center">
          <div className="flex items-center gap-1.5">
            <span
              className={`min-w-0 truncate font-extrabold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-400 ${nameSize}`}
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
          <p
            className={`mt-1 truncate text-xs text-slate-500 dark:text-slate-400`}
          >
            {r.sector || "기타"} ·{" "}
            {(r.trading_value / 1e8).toLocaleString("ko-KR", {
              maximumFractionDigits: 0,
            })}
            억
          </p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <div
            className={`text-sm font-extrabold text-slate-900 dark:text-slate-100`}
          >
            {r.current_price.toLocaleString("ko-KR")}
            <span className={`ml-0.5 text-[10px] font-bold text-slate-400`}>
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
          {/* 데스크탑 1등 카드는 아래 근거 줄이 우측 열로 빠지므로, 점수를 가격·등락률과
              같은 숫자 열에 모은다(모바일·일반 카드는 근거 줄 오른쪽에 그대로 있다). */}
          {featured && (
            <div className="mt-1 hidden lg:block">
              <ScoreBadge score={r.score} />
            </div>
          )}
        </div>
      </div>

      {/* 왜 뽑혔나 + 점수 — 한 줄. 예전엔 라벨 붙은 박스 + 점수 줄이 따로였는데,
          홈에서 카드 10장이 세로로 쌓이면 그만큼 시장 지표가 화면 밖으로 밀렸다.
          플라스크 아이콘이 '선정 근거'를 대신 표시하고, 전체 규칙은 title 에 남긴다.
          1등 카드는 데스크탑에서 이 줄을 우측 '왜 이 종목인가' 열이 대신한다. */}
      <div
        className={`mt-2.5 flex items-center gap-1.5 ${featured ? "lg:hidden" : ""}`}
      >
        <FlaskConical
          className={`h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500 ${
            featured ? "lg:h-4 lg:w-4" : ""
          }`}
        />
        <p
          title={ruleTitles.length > 0 ? ruleTitles.join(", ") : undefined}
          className={`min-w-0 flex-1 truncate text-xs font-bold text-slate-700 dark:text-slate-200`}
        >
          {reasonText}
        </p>
        <ScoreBadge score={r.score} />
      </div>

      {/* 선정 근거 — **1등 카드 + lg 이상에서만**. 카드 전체 폭을 쓰는 한 단 낮은 면이고,
            열로 쪼개지 않는다(2026-08-11 좌우 2단 기각). 두 줄 고정:
              1) 이 종목을 지목한 **규칙 이름 칩** — 설명도 상태 배지도 붙이지 않는다.
                 설명까지 펴면 카드가 규칙 해설판이 되고(설명은 스코어보드에 있다), 선정에
                 쓰이는 규칙은 `list_rules(status='live')` 뿐이라 상태는 항상 '적용중'이다.
              2) **뉴스 한 줄** — 배수 라벨은 홈 뉴스·재료 목록과 같은 `lib/news.newsHeatLabel`.
                 뉴스가 없는 날도 줄을 없애지 않고 '당일 뉴스 없음'을 낸다 — 줄이 사라지면
                 카드 높이가 날마다 달라지고, 뉴스가 없다는 사실 자체가 읽을 값이다.
            여백은 `p-2.5`·`gap-1.5` 로 조인다 — 두 줄짜리 블록이라 `p-3`·`gap-2` 로 두면
            카드가 `HERO_ROW_H`(224px) 하한을 넘겨 우측 성적 카드와 상단 정렬이 깨진다.
            ⚠️ 룰 성적 수치(승률·평균 수익)는 넣지 않는다 — 종목 옆에 붙으면 **그 종목의
            확률**로 읽힌다. 뉴스 배수도 색을 손익 방향(빨강/파랑)으로 쓰지 않는다. */}
      {featured && rules.length > 0 && (
        <div className={`mt-2.5 hidden flex-col gap-1.5 p-2.5 lg:flex ${INSET}`}>
          <div className="flex flex-wrap items-center gap-1.5">
            <FlaskConical className="mr-0.5 h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
            {rules.slice(0, RULE_CHIPS).map((rule) => (
              <span
                key={rule.name}
                className="shrink-0 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-extrabold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"
              >
                {rule.title || rule.name}
              </span>
            ))}
            {rules.length > RULE_CHIPS && (
              <span className="text-[11px] font-bold text-slate-400 dark:text-slate-500">
                외 {rules.length - RULE_CHIPS}개
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <Newspaper className="mr-0.5 h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
            {newsHeat ? (
              <>
                <span
                  className={`shrink-0 text-xs font-extrabold ${
                    newsHeat.emphasis
                      ? "text-slate-700 dark:text-slate-200"
                      : "text-slate-400 dark:text-slate-500"
                  }`}
                >
                  {newsHeat.headline}
                </span>
                {r.news_catalyst && (
                  <span className="shrink-0 rounded-full bg-slate-200/70 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700/60 dark:text-slate-300">
                    {r.news_catalyst}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-slate-400 tabular-nums dark:text-slate-500">
                  {newsHeat.detail}
                </span>
              </>
            ) : (
              <span className="text-xs font-bold text-slate-400 dark:text-slate-500">
                당일 뉴스 없음
              </span>
            )}
          </div>
        </div>
      )}

      {/* 배지 + 다음날 아침 갭 결과(NXT·KRX) — 한 줄에 묶는다.
          누적(리포트가 → KRX)은 카드에 찍지 않는다 — 한쪽 장만 있는 날엔 바로 앞 값과
          같은 숫자가 두 번 나오고, 둘 다 있는 날의 누적은 리포트 상세가 명시 라벨로 낸다.
          카드에서 누적은 배경 톤(`gapTone`)과 목록 하단 평균이 대신 말한다. */}
      <div
        className={`mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-bold`}
      >
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-extrabold ${
            GRADE_TONE[r.supply_grade] || GRADE_TONE.D
          }`}
        >
          수급 {r.supply_grade}
        </span>
        {/* 1등 카드는 데스크탑에서 위 근거 블록의 뉴스 줄이 같은 건수를 이미 말한다 —
            한 카드에 같은 숫자를 두 번 찍지 않는다. */}
        {(r.news_count ?? 0) > 0 && (
          <span
            className={`shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 ${
              featured ? "lg:hidden" : ""
            }`}
          >
            뉴스 {r.news_count}
          </span>
        )}
        {/* 무상증자 권리락일(sql/50) — 아래 등락률이 조정 기준가 대비임을 밝힌다.
            (없으면 배정비율만큼 낮아진 기준가 때문에 오른 종목이 하락으로 읽힌다) */}
        {r.gap_ex_rights_ratio != null && (
          <span
            title="무상증자 권리락일입니다 — 배정비율만큼 낮아진 권리락 기준가 대비 등락률입니다"
            className={`shrink-0 rounded-full bg-amber-200/80 px-1.5 py-0.5 text-[10px] font-extrabold text-amber-900 dark:bg-amber-900/50 dark:text-amber-200`}
          >
            권리락
          </span>
        )}

        {gapLines.length > 0 && (
          <span className="ml-auto flex shrink-0 items-baseline gap-2">
            {gapLines.map((g) => (
              <span
                key={g.label}
                className="inline-flex items-baseline gap-0.5"
              >
                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                  {g.label}
                </span>
                <span className={`tabular-nums ${pctColor(g.pct)}`}>
                  {g.pct > 0 ? "+" : ""}
                  {g.pct.toFixed(2)}%
                </span>
              </span>
            ))}
          </span>
        )}
      </div>
    </Link>
  );
}

/** 종합 점수 배지 — 일반 카드는 근거 줄 오른쪽, 1등 카드(데스크탑)는 가격 열 아래에 같은 모양으로
 *  붙는다. 두 자리에 같은 마크업을 두 벌 두지 않으려고 뺀 것뿐이라 로직은 없다. */
function ScoreBadge({ score }: { score: number }) {
  return (
    <span className="inline-block shrink-0 rounded-lg bg-indigo-50 px-1.5 py-0.5 tabular-nums dark:bg-indigo-950/50">
      <span className="text-sm font-extrabold text-indigo-700 dark:text-indigo-300">
        {score.toFixed(0)}
      </span>
      <span className="text-[10px] font-bold text-indigo-400 dark:text-indigo-400/70">
        점
      </span>
    </span>
  );
}
