"use client";

import { useId } from "react";

/**
 * 카드 배경용 라인 스파크라인 (인라인 SVG).
 * 좌표는 0~100 viewBox 에 정규화하고 preserveAspectRatio="none" 으로 카드에 꽉 채운다.
 * 텍스트 가독성을 위해 부모에서 낮은 opacity 로 깔아두는 용도.
 */
export function Sparkline({
  data,
  tone,
  className = "",
}: {
  data: number[];
  tone: "up" | "down" | "flat";
  className?: string;
}) {
  const id = useId();
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const n = data.length;

  // y는 위로 갈수록 0 → 값이 클수록 위쪽이 되도록 반전
  const points = data.map((v, i) => {
    const x = (i / (n - 1)) * 100;
    const y = 100 - ((v - min) / span) * 100;
    return [x, y] as const;
  });

  const linePath = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L100,100 L0,100 Z`;

  const stroke =
    tone === "up"
      ? "rgb(225 29 72)" // rose-600
      : tone === "down"
        ? "rgb(37 99 235)" // blue-600
        : "rgb(100 116 139)"; // slate-500

  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#spark-${id})`} stroke="none" />
      <path
        d={linePath}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        opacity="0.55"
      />
    </svg>
  );
}
