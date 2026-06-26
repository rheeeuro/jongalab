/** 표시용 공통 포맷터 (토스 스타일: 큰 숫자·간결). */

// 원 단위 축약 (+/- 부호, 억/만). 0 은 "0원".
export function won(v: number): string {
  const n = Math.round(v || 0);
  if (n === 0) return "0원";
  const sign = n > 0 ? "+" : "-";
  const a = Math.abs(n);
  if (a >= 100_000_000) return `${sign}${(a / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}억원`;
  if (a >= 10_000) return `${sign}${(a / 10_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}만원`;
  return `${sign}${a.toLocaleString()}원`;
}

// 정확한 원 표기 (가격 등)
export function wonExact(v: number): string {
  return `${Math.round(v || 0).toLocaleString()}원`;
}

// 달력 칸용 초압축 표기 (+/- 부호, 천/만/억, '원' 생략). 0 은 빈 문자열.
// precise=true 면 만 단위를 소수점 1자리까지 표기(넓은 화면용).
export function wonCompact(v: number, precise = false): string {
  const n = Math.round(v || 0);
  if (n === 0) return "";
  const sign = n > 0 ? "+" : "-";
  const a = Math.abs(n);
  if (a >= 100_000_000) return `${sign}${(a / 100_000_000).toFixed(1)}억`;
  if (a >= 10_000)
    return `${sign}${
      precise ? (a / 10_000).toLocaleString(undefined, { maximumFractionDigits: 1 }) : Math.round(a / 10_000)
    }만`;
  if (a >= 1_000) return `${sign}${Math.round(a / 1_000)}천`;
  return `${sign}${a}`;
}

// 수익률 표기 (+/- 부호, 소수 1자리). 분모 0/누락이면 null.
export function pct(pnl: number, base: number): string | null {
  if (!base) return null;
  const v = (pnl / base) * 100;
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}${Math.abs(v).toFixed(1)}%`;
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

// ISO(naive local) → "n초 전 / n분 전 / n시간 전". 모니터 마지막 폴링 표시용.
export function ago(iso: string | null, nowMs: number): string {
  if (!iso) return "기록 없음";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "기록 없음";
  const s = Math.max(0, Math.round((nowMs - t) / 1000));
  if (s < 60) return `${s}초 전`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}분 전`;
  return `${Math.floor(m / 60)}시간 전`;
}

// "2026-06-26T08:01:13" → "08:01:13"
export function hhmmss(iso: string): string {
  return iso.slice(11, 19);
}
