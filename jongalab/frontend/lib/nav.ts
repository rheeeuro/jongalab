import {
  CandlestickChart,
  FlaskConical,
  LineChart,
  Newspaper,
  Trophy,
  type LucideIcon,
} from "lucide-react";

/** 전역 내비게이션 단일 소스 — 데스크탑 Navbar 와 모바일 하단 탭이 같은 목록을 쓴다.
 *
 * **목적지는 5개로 고정한다.** 계층(서브탭)을 얹는 대신 화면을 합쳐서 줄인 결과이며,
 * 모바일 하단 탭 5칸에 정확히 맞아 '더보기' 시트가 필요 없다(1클릭 = 모든 화면).
 * 여기에 항목을 더하려면 먼저 어떤 화면을 합칠지 정한다.
 */
export type NavItem = {
  href: string;
  label: string;
  desc: string;
  icon: LucideIcon;
  /** 활성 판정 — exact 는 정확히 일치할 때만(홈), 기본은 prefix 매칭 */
  match?: "exact";
  /** 이 탭이 대표하는 하위 경로(탭에서 강등된 화면 포함) */
  owns?: string[];
};

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/",
    label: "추천",
    desc: "오늘의 추천 종목",
    icon: CandlestickChart,
    match: "exact",
    owns: ["/stocks"],
  },
  { href: "/record", label: "성적", desc: "날짜별 추천 성적", icon: Trophy, owns: ["/reports"] },
  {
    href: "/news",
    label: "뉴스",
    desc: "종목 재료·콘텐츠",
    icon: Newspaper,
    owns: ["/feed"],
  },
  {
    href: "/market",
    label: "시장",
    desc: "지수·섹터",
    icon: LineChart,
    owns: ["/sectors"],
  },
  { href: "/lab", label: "실험실", desc: "선정 규칙 검증", icon: FlaskConical },
];

export function isActiveNav(pathname: string, item: NavItem): boolean {
  if (item.match === "exact") {
    if (pathname === item.href) return true;
  } else if (pathname.startsWith(item.href)) {
    return true;
  }
  return (item.owns ?? []).some((p) => pathname.startsWith(p));
}
