import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { NewsDurability } from "@/types";

/**
 * 재료 지속성 칩 — 연속 / 중립 / 소진 / 미판정.
 *
 * ⚠️ **색을 손익 방향(빨강/파랑)으로 쓰지 않는다.** 이 라벨은 아직 candidate rule 표본이라
 * 검증되지 않았고, "연속=사라"로 읽히면 게이트 통과를 '검증됨'으로 오독하는 문제의 UI 버전이
 * 된다. 그래서 배경은 중립 회색 계열로 두고 **방향은 화살표로만** 표시하며, title 에
 * '관찰 중(미검증)'을 명시한다.
 *
 * 모바일 우선: 한 줄 칩(높이 20px), 텍스트는 잘리지 않게 shrink-0.
 */

const STYLE: Record<
  Exclude<NewsDurability, null> | "미판정",
  { label: string; hint: string; cls: string; Icon: typeof ArrowUpRight }
> = {
  연속: {
    label: "연속",
    hint: "다음 예정 사건이 남은 재료 (관찰 중 · 미검증)",
    cls: "bg-slate-100 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700",
    Icon: ArrowUpRight,
  },
  소진: {
    label: "소진",
    hint: "수치가 확정되고 다음 일정이 없는 재료 (관찰 중 · 미검증)",
    cls: "bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700",
    Icon: ArrowDownRight,
  },
  중립: {
    label: "중립",
    hint: "지속성이 한쪽으로 갈리지 않는 재료 (관찰 중 · 미검증)",
    cls: "bg-slate-50 text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700",
    Icon: Minus,
  },
  미판정: {
    label: "미판정",
    hint: "재료를 특정할 수 없어 판정하지 않음 (억지로 채우지 않는다)",
    cls: "bg-transparent text-slate-400 ring-1 ring-dashed ring-slate-300 dark:text-slate-500 dark:ring-slate-600",
    Icon: Minus,
  },
};

export function MaterialBadge({
  durability,
  showUnjudged = false,
  className = "",
}: {
  durability?: NewsDurability;
  /** 미판정도 칩으로 보여줄지 (상세 화면=true, 목록=false 로 노이즈 억제) */
  showUnjudged?: boolean;
  className?: string;
}) {
  const key = durability ?? "미판정";
  if (key === "미판정" && !showUnjudged) return null;

  const { label, hint, cls, Icon } = STYLE[key];
  return (
    <span
      title={hint}
      className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-bold ${cls} ${className}`}
    >
      <Icon className="h-3 w-3" strokeWidth={2.5} />
      {label}
    </span>
  );
}

/** 사실 4축을 사람 말로 — 등급만 보면 왜 그렇게 판정됐는지 알 수 없어 감사가 안 된다. */
export function materialAxisLabels(r: {
  news_next_milestone?: boolean | null;
  news_amount_locked?: boolean | null;
  news_driver_scope?: string | null;
  news_stage?: string | null;
}): string[] {
  const out: string[] = [];
  if (r.news_next_milestone != null)
    out.push(r.news_next_milestone ? "다음 일정 남음" : "다음 일정 없음");
  if (r.news_amount_locked != null)
    out.push(r.news_amount_locked ? "수치 확정" : "수치 미확정");
  if (r.news_driver_scope && r.news_driver_scope !== "불명")
    out.push(r.news_driver_scope === "산업사이클" ? "산업 사이클" : "종목 단독");
  if (r.news_stage && r.news_stage !== "불명") out.push(r.news_stage);
  return out;
}
