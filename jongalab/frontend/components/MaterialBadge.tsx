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
    hint: "한 달 안에 관련 일정이 남아 있거나, 업종 흐름을 타고 있는 이유예요 (지켜보는 중 · 아직 검증 안 됨)",
    cls: "bg-slate-100 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700",
    Icon: ArrowUpRight,
  },
  소진: {
    label: "소진",
    hint: "남은 일정이 없거나 이미 마무리된 이유예요 (지켜보는 중 · 아직 검증 안 됨)",
    cls: "bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700",
    Icon: ArrowDownRight,
  },
  중립: {
    label: "중립",
    hint: "일정은 남았지만 언제인지 멀거나 확실하지 않은 이유예요 (지켜보는 중 · 아직 검증 안 됨)",
    cls: "bg-slate-50 text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700",
    Icon: Minus,
  },
  미판정: {
    label: "미판정",
    hint: "왜 움직였는지 딱 집을 수 없어서 비워 뒀어요 (억지로 고르지 않아요)",
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

/** 사실 축을 사람 말로 — 등급만 보면 왜 그렇게 판정됐는지 알 수 없어 감사가 안 된다.
 *
 * 순서가 **등급을 가르는 순서**와 같다(다음 일정 → 그 시점 → 사이클 → 국면). v2 부터
 * 등급을 실제로 가르는 축은 '시점'이고 '수치 확정'은 합성에서 빠졌으므로, 수치는 참고 축으로
 * 뒤에 둔다 — 화면이 등급에 안 쓰이는 축을 앞세우면 감사가 엉뚱한 곳을 본다. */
export function materialAxisLabels(r: {
  news_next_milestone?: boolean | null;
  news_milestone_horizon?: string | null;
  news_amount_locked?: boolean | null;
  news_material_size_ratio?: number | null;
  news_driver_scope?: string | null;
  news_stage?: string | null;
}): string[] {
  const out: string[] = [];
  if (r.news_next_milestone != null)
    out.push(r.news_next_milestone ? "다음 일정 남음" : "다음 일정 없음");
  if (r.news_milestone_horizon && r.news_milestone_horizon !== "불명")
    out.push(`일정 ${r.news_milestone_horizon}`);
  if (r.news_driver_scope && r.news_driver_scope !== "불명")
    out.push(r.news_driver_scope === "산업사이클" ? "산업 사이클" : "종목 단독");
  if (r.news_stage && r.news_stage !== "불명") out.push(r.news_stage);
  if (r.news_amount_locked != null)
    out.push(r.news_amount_locked ? "수치 확정" : "수치 미확정");
  // 재료 규모는 시총 대비 비율이라야 뜻이 있다(같은 1,200억이 시총 3천억과 400조에 다르다).
  if (r.news_material_size_ratio != null && r.news_material_size_ratio > 0)
    out.push(`규모 시총의 ${(r.news_material_size_ratio * 100).toFixed(1)}%`);
  return out;
}
