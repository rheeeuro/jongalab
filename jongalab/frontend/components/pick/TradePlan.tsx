import { LogIn, LogOut, ShieldAlert } from "lucide-react";
import { StockReport } from "@/types";
import { FixedLossCalculator } from "@/components/FixedLossCalculator";

/** 어떻게 매매하나 — 이 사이트의 성적이 어떤 가정 위에 있는지를 그대로 적는다.
 *
 * 진입(종가) → 청산(익일 시가)이 성적 집계의 전제이므로, 그 전제를 화면에 밝히지 않으면
 * 사용자는 자기 매매 방식으로 같은 성적이 날 거라 오해한다. 손절 폭은 사람마다 다르므로
 * 숫자를 정해 주지 않고 **계산기**만 붙인다(권유가 아니라 도구).
 */
export function TradePlan({ report: r }: { report: StockReport }) {
  const steps = [
    {
      icon: LogIn,
      label: "진입",
      value: `${r.current_price.toLocaleString("ko-KR")}원`,
      note: "리포트를 만든 때(장 마감 무렵) 가격이에요",
    },
    {
      icon: LogOut,
      label: "청산",
      value: "다음 거래일 시가",
      note: "성적을 셀 때 쓰는 기준이에요",
    },
    {
      icon: ShieldAlert,
      label: "손절",
      value: "직접 설정",
      note: "잃어도 괜찮은 금액을 정하고 수량을 거꾸로 계산해 보세요",
    },
  ];

  return (
    <section className="rounded-3xl bg-white p-5 sm:p-6 dark:bg-slate-900/60">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-extrabold text-slate-900 dark:text-slate-100">
          어떻게 매매하나
        </h2>
        <FixedLossCalculator ticker={r.stock_code} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {steps.map(({ icon: Icon, label, value, note }) => (
          <div
            key={label}
            className="rounded-2xl bg-slate-50 px-3.5 py-3 dark:bg-slate-800/40"
          >
            <p className="flex items-center gap-1.5 text-[11px] font-extrabold text-slate-400 dark:text-slate-500">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </p>
            <p className="mt-1 text-base font-black tabular-nums text-slate-900 dark:text-slate-100">
              {value}
            </p>
            <p className="mt-0.5 text-[11px] leading-snug font-medium text-slate-400 dark:text-slate-500">
              {note}
            </p>
          </div>
        ))}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
        성적 화면의 승률·평균 수익률은 이렇게(장 마감에 사서 다음 날 아침에 팔기) 했다고 보고
        계산한 값이에요. 다르게 매매하면 결과도 달라져요.
      </p>
    </section>
  );
}
