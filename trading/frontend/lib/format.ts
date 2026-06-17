/** 표시용 공통 포맷터 (토스 스타일: 큰 숫자·간결). */

// 원 단위 축약 (+/- 부호, 억/만). 0 은 "0원".
export function won(v: number): string {
  const n = Math.round(v || 0);
  if (n === 0) return "0원";
  const sign = n > 0 ? "+" : "-";
  const a = Math.abs(n);
  if (a >= 100_000_000) return `${sign}${(a / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}억원`;
  if (a >= 10_000) return `${sign}${Math.round(a / 10_000).toLocaleString()}만원`;
  return `${sign}${a.toLocaleString()}원`;
}

// 정확한 원 표기 (가격 등)
export function wonExact(v: number): string {
  return `${Math.round(v || 0).toLocaleString()}원`;
}

// 달력 칸용 초압축 표기 (+/- 부호, 천/만/억, '원' 생략). 0 은 빈 문자열.
export function wonCompact(v: number): string {
  const n = Math.round(v || 0);
  if (n === 0) return "";
  const sign = n > 0 ? "+" : "-";
  const a = Math.abs(n);
  if (a >= 100_000_000) return `${sign}${(a / 100_000_000).toFixed(1)}억`;
  if (a >= 10_000) return `${sign}${Math.round(a / 10_000)}만`;
  if (a >= 1_000) return `${sign}${Math.round(a / 1_000)}천`;
  return `${sign}${a}`;
}

// 손익 색상 (국내 관례: 이익 빨강 / 손실 파랑 / 0 회색)
export function pnlClass(v: number): string {
  if (v > 0) return "text-rose-500";
  if (v < 0) return "text-blue-500";
  return "text-slate-400";
}

// YYYYMMDD → "6월 17일 (수)"
const WD = ["일", "월", "화", "수", "목", "금", "토"];
export function fmtDate(yyyymmdd: string): string {
  const y = +yyyymmdd.slice(0, 4);
  const m = +yyyymmdd.slice(4, 6);
  const d = +yyyymmdd.slice(6, 8);
  const wd = WD[new Date(y, m - 1, d).getDay()];
  return `${m}월 ${d}일 (${wd})`;
}

export function todayYYYYMMDD(): string {
  const n = new Date();
  return `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, "0")}${String(n.getDate()).padStart(2, "0")}`;
}
