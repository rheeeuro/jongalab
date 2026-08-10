/** 표면(surface) 토큰 — 카드가 배경과 구분되게 하는 최소 규칙.
 *
 * 페이지 배경이 `#F9FAFB`(dark `#0F0F12`)라 **흰 카드만으로는 경계가 보이지 않는다**.
 * 그래서 모든 카드는 배경색이 아니라 **헤어라인 링**으로 경계를 만든다(그림자는 보조).
 *
 * 3단계만 쓴다 — 더 늘리면 어느 것이 위 계층인지 화면에서 읽히지 않는다.
 *   L0 페이지 배경 (`app/layout.tsx`)
 *   L1 `CARD`  — 페이지 위에 놓이는 카드
 *   L2 `INSET` — 카드 **안**에 들어가는 영역(차트 트랙·보조 블록)
 *
 * ⚠️ **강조를 표면 반전(어두운 패널)으로 만들지 말 것.** 라이트모드에서만 강조가 되고
 * 다크모드에서는 다른 카드와 같은 어두운 상자가 되어 강조가 사라진다(2026-08-10 실패).
 * 강조는 **크기·구조**로 준다 — 히어로 숫자, 미터, 안쪽 한 단 낮은 면.
 */
export const CARD =
  "rounded-2xl bg-white ring-1 ring-slate-200/70 shadow-sm dark:bg-slate-900/70 dark:shadow-none dark:ring-white/5";

export const INSET = "rounded-lg bg-slate-100 dark:bg-slate-800/60";

/** 카드 호버 — 목록 안의 누를 수 있는 카드에만 붙인다. */
export const CARD_HOVER =
  "transition-all hover:-translate-y-0.5 hover:shadow-md";
