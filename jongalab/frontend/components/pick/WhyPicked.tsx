import { Activity, BarChart3, Newspaper } from "lucide-react";
import { StockReport } from "@/types";
import { PANEL } from "@/lib/ui";
import { SCORE_AXES, type Rich } from "@/lib/report";
import { RichText } from "@/components/ui/rich-text";

const GRADE_NOTE: Record<string, string> = {
  S: "종가베팅 최우선",
  A: "관심권",
  B: "조건부 관찰",
  C: "수급 약함",
  D: "수급 기여 없음",
};

function billion(v: number): string {
  const b = v / 1e8;
  return `${b > 0 ? "+" : ""}${b.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억`;
}

/** 수급 축 한 줄 — 누가 얼마나 샀는지. */
function supplyLine(r: StockReport): string {
  const buyers: string[] = [];
  if (r.inst_net_buy > 0) buyers.push(`기관 ${billion(r.inst_net_buy)}`);
  if (r.frgn_net_buy > 0) buyers.push(`외국인 ${billion(r.frgn_net_buy)}`);
  if (r.prog_net_buy > 0) buyers.push(`프로그램 ${billion(r.prog_net_buy)}`);
  if (buyers.length === 0) return "기관·외국인이 사지 않았어요";
  const days = r.supply_days > 0 ? ` · ${r.supply_days}일 연속` : "";
  return `${buyers.join(" · ")}${days}`;
}

/** 기술 축 한 줄 — 추세와 위치. */
function technicalLine(r: StockReport): string {
  const parts: string[] = [];
  if (r.ma_aligned) parts.push("이동평균 정배열");
  if (r.near_high) parts.push("신고가 근접");
  if (r.is_leader) parts.push(`${r.sector || "섹터"} 대장주`);
  if (parts.length === 0) return "차트에서 눈에 띄는 신호는 없어요";
  return parts.join(" · ");
}

/** 재료 축 한 줄 — 뉴스·콘텐츠. */
function materialLine(r: StockReport): string {
  const parts: string[] = [];
  if (r.is_theme_stock) parts.push("오늘의 테마주");
  if ((r.news_count ?? 0) > 0) {
    parts.push(
      `뉴스 ${r.news_count}건${r.news_catalyst ? ` (${r.news_catalyst})` : ""}`,
    );
  }
  if ((r.content_score ?? 0) > 0) parts.push("유튜브·텔레그램 언급");
  if (parts.length === 0) return "이 날 모아 온 재료가 없어요";
  return parts.join(" · ");
}

/** 왜 뽑혔나 — 선정 근거를 수급·기술·재료 세 축으로 상세 상단에 요약한다.
 *
 * 아래 상세 표(수급 동향·차트·뉴스)를 다 읽어야 알 수 있던 것을 먼저 한 줄씩 낸다.
 * ⚠️ 여기 문구는 **저장된 리포트 값을 그대로 서술**할 뿐 새로 판정하지 않는다 —
 * 화면이 조건을 재추정하면 서버와 어긋난다(README '조건 판정은 서버만' 규칙).
 */
export function WhyPicked({
  report: r,
  lede = [],
}: {
  report: StockReport;
  /** 도입 문단(`lib/report.reportLede`) — 카드 안에 두어야 줄글이 '떠 있는 회색 블록'이 되지 않는다. */
  lede?: Rich[];
}) {
  // 아이콘 색은 종합점수 게이지의 축 색과 **같은 소스**를 쓴다 — 색이 두 카드를 잇는 열쇠다.
  const tone = Object.fromEntries(SCORE_AXES.map((a) => [a.label, a.text]));
  const axes = [
    {
      icon: Activity,
      label: "수급",
      badge: `${r.supply_grade}등급 ${r.supply_score.toFixed(0)}점`,
      note: GRADE_NOTE[r.supply_grade] ?? "",
      text: supplyLine(r),
    },
    {
      icon: BarChart3,
      label: "기술",
      badge: `${r.change_pct > 0 ? "+" : ""}${r.change_pct.toFixed(2)}%`,
      note: "당일 등락",
      text: technicalLine(r),
    },
    {
      icon: Newspaper,
      label: "재료",
      badge: `${r.news_count ?? 0}건`,
      note: "당일 뉴스",
      text: materialLine(r),
    },
  ];

  return (
    <section className={PANEL}>
      {/* 넓은 화면(lg+)은 **[제목+줄글] 왼쪽 / 근거 3축 오른쪽** 2열이다.
          줄글은 한 줄 길이를 40~50자로 묶어야 읽히는데(전체 폭으로 흘리면 눈이 줄을 놓친다),
          그러면 한 열짜리 배치에서는 카드 오른쪽이 통째로 빈다. 성격이 다른 두 블록이
          각자 한 열을 채우게 두면 줄 길이도 지키고 빈 칸도 생기지 않는다.
          **제목을 왼쪽 열 안에 두는 것이 핵심**이다 — 제목 밖에 두면 3축이 제목 아래에서 시작해
          카드 오른쪽 위가 빈다. 두 열은 위·아래끝을 함께 맞춘다. */}
      <div className="lg:grid lg:grid-cols-2 lg:gap-6">
        <div className="lg:flex lg:h-full lg:flex-col">
          {/* 점수·순위는 종합점수 게이지와 헤더 배지가 낸다 — 여기 다시 적으면 한 화면에 세 번이다. */}
          <h2 className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
            왜 뽑혔나
          </h2>

          {lede.length > 0 && (
            // 남는 세로 공간은 **문단 사이**에 분산해 오른쪽 3축과 아래끝을 맞춘다
            // (아래로 몰면 그게 곧 '왼쪽 아래가 비었다'가 된다 — 홈 카드와 같은 규칙).
            <div className="mt-3.5 max-w-[68ch] space-y-2 text-sm leading-6 break-keep text-slate-500 lg:mt-4 lg:flex lg:flex-1 lg:flex-col lg:justify-between lg:gap-2 lg:space-y-0 dark:text-slate-400">
              {lede.map((parts, i) => (
                <p key={i}>
                  <RichText parts={parts} />
                </p>
              ))}
            </div>
          )}
        </div>

        {/* 근거 3축 — 모바일 1열 · 태블릿 가로 3열 · lg+ 오른쪽 열에 세로로 쌓는다. */}
        <div className="mt-4 grid gap-2.5 md:grid-cols-3 lg:mt-0 lg:flex lg:h-full lg:flex-col lg:justify-between">
          {axes.map(({ icon: Icon, label, badge, note, text }) => (
            <div
              key={label}
              className="flex h-full items-start gap-3 rounded-2xl bg-slate-50 px-3.5 py-3 dark:bg-slate-800/40"
            >
              <span
                className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white dark:bg-slate-900 ${tone[label] ?? "text-slate-500 dark:text-slate-400"}`}
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline gap-x-1.5 text-xs font-extrabold text-slate-500 dark:text-slate-400">
                  {label}
                  <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] tabular-nums text-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    {badge}
                  </span>
                  {note && (
                    <span className="font-medium text-slate-400 dark:text-slate-500">
                      {note}
                    </span>
                  )}
                </p>
                <p className="mt-1 text-sm leading-relaxed font-bold break-keep text-slate-800 dark:text-slate-100">
                  {text}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
