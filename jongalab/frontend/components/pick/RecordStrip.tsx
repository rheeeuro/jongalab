import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { RecordSummary } from "@/types";
import { CARD, HERO_ROW_H, INSET } from "@/lib/ui";

function signed(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

/** 최근 N 거래일 누적 성적 — "얼마나 믿을 수 있나"에 답하는 화면의 **히어로 수치**다.
 *
 * 강조는 **표면이 아니라 크기와 구조**로 준다. 배경을 반전시켜(라이트=검정 패널) 띄우면
 * 다크모드에서는 다른 카드와 같은 어두운 상자가 되어 강조가 사라진다 — 실제로 그랬다.
 * 지금은 두 모드 모두 같은 카드 표면 위에서 48px 승률 숫자 하나가 화면의 유일한
 * 대형 숫자다(h1 도 30px). 화면당 히어로 숫자는 하나만 둔다.
 *
 * 승률은 **미터**로 낸다(0~100% 한계 대비 비율). 승/패를 두 색 구간으로 쪼개지 않는 이유는
 * 2구간 비율 그래프가 숫자보다 덜 읽히기 때문이다 — 패는 `103승 83패` 라벨이 그대로 낸다.
 * 트랙은 같은 색 계열의 옅은 단계(rose 15%)라 채움과 트랙이 한 눈금자로 읽힌다.
 *
 * 승률·평균 갭은 **선정 종목 전체**(selected=1, 갭 체크 완료)가 모수다. 평균 실체결은
 * 매매 경로에서 채워져 표본이 더 적을 수 있어(`exec_samples`) 모수가 다르면 그 사실을
 * 화면에 적는다 — 두 수치를 같은 모수로 읽으면 성적이 부풀려진다.
 */
export function RecordStrip({
  summary,
  href = "/record",
}: {
  summary: RecordSummary | null;
  href?: string;
}) {
  if (!summary || summary.picks === 0) return null;

  // 실체결 라벨 구간이 갭 구간과 다르면 그 사실을 부제에 적는다 —
  // 같은 창의 값처럼 나란히 놓으면 성적이 부풀려 읽힌다.
  const execWindowDiffers =
    summary.avg_exec_ret !== null && summary.exec_days !== summary.days;

  return (
    // `HERO_ROW_H` 는 홈 2단에서 좌측 1등 픽 카드와 **높이를 맞추기 위한 공통 하한**이다
    // (어긋나면 그만큼 우측 뉴스 카드 상단이 좌측 2·3·4등 줄과 틀어진다).
    <Link href={href} className={`group block p-4 ${HERO_ROW_H} ${CARD}`}>
      <div className="flex items-center gap-1.5">
        <p className="text-[11px] font-extrabold tracking-wide text-slate-400 uppercase dark:text-slate-500">
          최근 {summary.days}거래일 성적
        </p>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
          · {summary.picks}종목
        </span>
        <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600" />
      </div>

      {/* 히어로 숫자 — 큰 단독 수치라 tabular-nums 를 쓰지 않는다(자릿폭이 벌어져 헐거워 보인다) */}
      <div className="mt-1.5 flex items-end justify-between gap-2">
        <div className="flex items-end gap-1.5">
          <span className="text-5xl leading-none font-black text-slate-900 dark:text-slate-100">
            {summary.win_rate.toFixed(0)}
          </span>
          <span className="mb-0.5 text-xl leading-none font-black text-slate-300 dark:text-slate-600">
            %
          </span>
          <span className="mb-1 text-xs font-bold text-slate-500 dark:text-slate-400">
            승률
          </span>
        </div>
        <p className="mb-1 text-xs font-bold text-slate-500 tabular-nums dark:text-slate-400">
          {summary.wins}승 {summary.losses}패
        </p>
      </div>

      <div
        className="mt-2.5 h-2 rounded-full bg-rose-500/15"
        role="img"
        aria-label={`승률 ${summary.win_rate.toFixed(0)}퍼센트 (${summary.wins}승 ${summary.losses}패)`}
      >
        <div
          className="h-full rounded-full bg-rose-500"
          style={{ width: `${Math.min(Math.max(summary.win_rate, 0), 100)}%` }}
        />
      </div>

      {/* 보조 지표는 카드 **안쪽** 한 단 낮은 면에 둔다 — 히어로와 같은 높이로 읽히지 않게 */}
      <div className={`mt-3 grid grid-cols-2 gap-3 p-3 ${INSET}`}>
        <Metric
          label="평균 갭"
          value={signed(summary.avg_gap_pct)}
          sub="종가→익일 시가"
          tone={pctTone(summary.avg_gap_pct)}
        />
        <Metric
          label="평균 실체결"
          value={
            summary.avg_exec_ret === null ? "—" : signed(summary.avg_exec_ret)
          }
          sub={
            summary.avg_exec_ret === null
              ? "집계 전"
              : execWindowDiffers
                ? `최근 ${summary.exec_days}거래일만`
                : "체결가 기준"
          }
          tone={
            summary.avg_exec_ret === null
              ? "text-slate-400"
              : pctTone(summary.avg_exec_ret)
          }
        />
      </div>
    </Link>
  );
}

function pctTone(pct: number): string {
  if (pct > 0) return "text-rose-600 dark:text-rose-400";
  if (pct < 0) return "text-blue-600 dark:text-blue-400";
  return "text-slate-600 dark:text-slate-300";
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: string;
}) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[10px] font-bold text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p className={`mt-0.5 truncate text-lg font-black tabular-nums ${tone}`}>
        {value}
      </p>
      <p className="truncate text-[10px] font-medium text-slate-400 dark:text-slate-500">
        {sub}
      </p>
    </div>
  );
}
